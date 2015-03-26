##########################################################################
#
# Copyright 2011 Jose Fonseca
# Copyright 2008-2010 VMware, Inc.
# All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
##########################################################################/


"""GLX tracing generator."""


from gltrace import GlTracer
from specs.stdapi import Module, API
from specs.glapi import glapi
from specs.glxapi import glxapi


class GlxTracer(GlTracer):

    def isFunctionPublic(self, function):
        # The symbols visible in libGL.so can vary, so expose them all
        return True

    getProcAddressFunctionNames = [
        "glXGetProcAddress",
        "glXGetProcAddressARB",
    ]

    createContextFunctionNames = [
        'glXCreateContext',
        'glXCreateContextAttribsARB',
        'glXCreateContextWithConfigSGIX',
        'glXCreateNewContext',
    ]

    destroyContextFunctionNames = [
        'glXDestroyContext',
    ]

    makeCurrentFunctionNames = [
        'glXMakeCurrent',
        'glXMakeContextCurrent',
        'glXMakeCurrentReadSGI',
    ]

    def traceFunctionImplBody(self, function):
        if function.name in self.destroyContextFunctionNames:
            print '    gltrace::releaseContext((uintptr_t)ctx);'

        GlTracer.traceFunctionImplBody(self, function)

        if function.name in self.createContextFunctionNames:
            print '    if (_result != NULL)'
            print '        gltrace::createContext((uintptr_t)_result);'

        if function.name in self.makeCurrentFunctionNames:
            print '    if (_result) {'
            print '        if (ctx != NULL)'
            print '            gltrace::setContext((uintptr_t)ctx);'
            print '        else'
            print '            gltrace::clearContext();'
            print '    }'

        if function.name == 'glXBindTexImageEXT':
            # FIXME: glXBindTexImageEXT gets called frequently, so we should
            # avoid recording the same data over and over again somehow, e.g.:
            # - get the pixels before and after glXBindTexImageEXT, and only
            #   emit emitFakeTexture2D when it changes
            # - keep a global hash of the pixels
            # FIXME: Handle mipmaps
            print r'''
                unsigned glx_target = 0;
                _glXQueryDrawable(display, drawable, GLX_TEXTURE_TARGET_EXT, &glx_target);
                GLenum target;
                switch (glx_target) {
                // FIXME
                //case GLX_TEXTURE_1D_EXT:
                //    target = GL_TEXTURE_1D;
                //    break;
                case GLX_TEXTURE_2D_EXT:
                    target = GL_TEXTURE_2D;
                    break;
                case GLX_TEXTURE_RECTANGLE_EXT:
                    target = GL_TEXTURE_RECTANGLE;
                    break;
                default:
                    os::log("apitrace: warning: %s: unsupported GLX_TEXTURE_TARGET_EXT 0x%u\n", __FUNCTION__, glx_target);
                    target = GL_NONE;
                    break;
                }
                GLint level = 0;
                GLint internalformat = GL_NONE;
                _glGetTexLevelParameteriv(target, level, GL_TEXTURE_INTERNAL_FORMAT, &internalformat);
                // XXX: GL_TEXTURE_INTERNAL_FORMAT cannot be trusted on NVIDIA
                // -- it sometimes returns GL_BGRA, even though GL_BGR/BGRA is
                // not a valid internal format.
                switch (internalformat) {
                case GL_BGR:
                    internalformat = GL_RGB;
                    break;
                case GL_BGRA:
                    internalformat = GL_RGBA;
                    break;
                }
                GLint width = 0;
                _glGetTexLevelParameteriv(target, level, GL_TEXTURE_WIDTH, &width);
                GLint height = 0;
                _glGetTexLevelParameteriv(target, level, GL_TEXTURE_HEIGHT, &height);
                GLint border = 0;
                // XXX: We always use GL_RGBA format to read the pixels because:
                // - some implementations (Mesa) seem to return bogus results
                //   for GLX_TEXTURE_FORMAT_EXT
                // - hardware usually stores GL_RGB with 32bpp, so it should be
                //   faster to read/write
                // - it is more robust against GL_(UN)PACK_ALIGNMENT state
                //   changes
                // The drawback is that traces will be slightly bigger.
                GLenum format = GL_RGBA;
                GLenum type = GL_UNSIGNED_BYTE;
                if (target && internalformat && height && width) {
                    // FIXME: This assumes (UN)PACK state (in particular
                    // GL_(UN)PACK_ROW_LENGTH) is set to its defaults. We
                    // really should temporarily reset the state here (and emit
                    // according fake calls) to cope when its not. At very
                    // least we need a heads up warning that this will cause
                    // problems.
                    GLint alignment = 4;
                    GLint row_stride = _align(width * 4, alignment);
                    GLvoid * pixels = malloc(height * row_stride);
                    _glGetTexImage(target, level, format, type, pixels);
            '''
            self.emitFakeTexture2D()
            print r'''
                    free(pixels);
                }
            '''


if __name__ == '__main__':
    print
    print '#include <stdlib.h>'
    print '#include <string.h>'
    print
    print '#include "trace_writer_local.hpp"'
    print
    print '// To validate our prototypes'
    print '#define GL_GLEXT_PROTOTYPES'
    print '#define GLX_GLXEXT_PROTOTYPES'
    print
    print '#include "dlopen.hpp"'
    print '#include "glproc.hpp"'
    print '#include "glsize.hpp"'
    print

    module = Module()
    module.mergeModule(glxapi)
    module.mergeModule(glapi)
    api = API()
    api.addModule(module)
    tracer = GlxTracer()
    tracer.traceApi(api)

    print r'''


/*
 * Several applications, such as Quake3, use dlopen("libGL.so.1"), but
 * LD_PRELOAD does not intercept symbols obtained via dlopen/dlsym, therefore
 * we need to intercept the dlopen() call here, and redirect to our wrapper
 * shared object.
 */
extern "C" PUBLIC
void * dlopen(const char *filename, int flag)
{
    void *handle;

    handle = _dlopen(filename, flag);

    const char * libgl_filename = getenv("TRACE_LIBGL");

    if (filename && handle && !libgl_filename) {
        if (0) {
            os::log("apitrace: warning: dlopen(\"%s\", 0x%x)\n", filename, flag);
        }

        // FIXME: handle absolute paths and other versions
        if (strcmp(filename, "libGL.so") == 0 ||
            strcmp(filename, "libGL.so.1") == 0) {

            // Use the true libGL.so handle instead of RTLD_NEXT from now on
            _libGlHandle = handle;

            // Get the file path for our shared object, and use it instead
            static int dummy = 0xdeedbeef;
            Dl_info info;
            if (dladdr(&dummy, &info)) {
                os::log("apitrace: redirecting dlopen(\"%s\", 0x%x)\n", filename, flag);
                handle = _dlopen(info.dli_fname, flag);
            } else {
                os::log("apitrace: warning: dladdr() failed\n");
            }
        }
    }

    return handle;
}


/*
 * Bookkeeping of textures for single frame capture mode.
 */

typedef struct {
    /*
     * already_saved flag to note if this texture was already written
     * to trace file.
     */
    bool    already_saved;
    GLenum  texture;
} texlistItem;

unsigned int live_textures(0);
size_t       texturelist_size(0);
texlistItem  *texturelist(NULL);
const int    growsize(2048);

extern "C" void storenewtextures(const GLsizei n, const GLuint * textures)
{
    if (texturelist_size <= live_textures+n)
    {
        void* newtexturelist = realloc((void*)texturelist,
                                    (texturelist_size+growsize)
                                    *sizeof(texlistItem));
        if (!newtexturelist) {
            os::log("apitrace: warning: realloc at storenewtextures failed\n");
            return;
        }
        texturelist = (texlistItem*)newtexturelist;
        texturelist_size += growsize;
    }

    for (unsigned c = 0, c2; c < n; c++) {
        for (c2 = 0; c2 < live_textures; c2++) {
            if (texturelist[c2].texture == textures[c]) {
                break;
            }
        }
        if (texturelist[c2].texture != textures[c] && textures[c] != 0) {
            texturelist[live_textures].texture = textures[c];
            texturelist[live_textures].already_saved = false;
            live_textures++;
        }
    }
}

extern "C" void removetextures(const GLsizei n, const GLuint *textures)
{
    for (unsigned c = 0; c < n; c++) {
        unsigned c2, s;

        for (c2 = 0, s = 0; c2+s < live_textures; c2++) {

            /*
             * found texture to be taken out?
             */
            if (texturelist[c2].texture == textures[c])
                s++;

            if (s > 0) {
                /*
                 * use memcpy here to be future-proof. Assumption is here
                 * will be added things at least because of texture view.
                 */
                memcpy((void*)(&texturelist[c2]), (void*)(&texturelist[c2+s]),
                               sizeof(texlistItem));
            }
        }
        live_textures -= s;
    }
}

void fakeglGenTextture(GLenum texture)
{
    unsigned _call = trace::localWriter.beginEnter(&_glGenTextures_sig);
    trace::localWriter.beginArg(0);
    trace::localWriter.writeSInt(1);
    trace::localWriter.endArg();
    trace::localWriter.endEnter();
    trace::localWriter.beginLeave(_call);
    trace::localWriter.beginArg(1);
    trace::localWriter.beginArray(1);
    trace::localWriter.beginElement();
    trace::localWriter.writeUInt(texture);
    trace::localWriter.endElement();
    trace::localWriter.endArray();
    trace::localWriter.endArg();
    trace::localWriter.endLeave();
}

void fakeglTexImage2D(GLenum target, GLint level, GLint internalformat,
                      GLsizei width, GLsizei height, GLint border,
                      GLenum format, GLenum type, const GLvoid * pixels)
{
    unsigned _call = trace::localWriter.beginEnter(&_glTexImage2D_sig);
    trace::localWriter.beginArg(0);
    trace::localWriter.writeEnum(&_enumGLenum_sig, target);
    trace::localWriter.endArg();
    trace::localWriter.beginArg(1);
    trace::localWriter.writeSInt(level);
    trace::localWriter.endArg();
    trace::localWriter.beginArg(2);
    trace::localWriter.writeEnum(&_enumGLenum_sig, internalformat);
    trace::localWriter.endArg();
    trace::localWriter.beginArg(3);
    trace::localWriter.writeSInt(width);
    trace::localWriter.endArg();
    trace::localWriter.beginArg(4);
    trace::localWriter.writeSInt(height);
    trace::localWriter.endArg();
    trace::localWriter.beginArg(5);
    trace::localWriter.writeSInt(border);
    trace::localWriter.endArg();
    trace::localWriter.beginArg(6);
    trace::localWriter.writeEnum(&_enumGLenum_sig, format);
    trace::localWriter.endArg();
    trace::localWriter.beginArg(7);
    trace::localWriter.writeEnum(&_enumGLenum_sig, type);
    trace::localWriter.endArg();
    trace::localWriter.beginArg(8);

    gltrace::Context *ctx = gltrace::getContext();
    GLint _unpack_buffer = 0;
    if (ctx->profile.desktop())
        _glGetIntegerv(GL_PIXEL_UNPACK_BUFFER_BINDING, &_unpack_buffer);

    if (_unpack_buffer) {
        trace::localWriter.writePointer((uintptr_t)pixels);
    }
    else {
        trace::localWriter.writeBlob(pixels, _glTexImage2D_size(format,
                                                                type, width,
                                                                height));
    }
    trace::localWriter.endArg();
    trace::localWriter.endEnter();
    trace::localWriter.beginLeave(_call);
    trace::localWriter.endLeave();
}


/*
 * Bookkeeping of shaders for single frame capture mode.
 */
typedef struct {
    bool        already_saved;
    GLenum      type;
    GLuint      shader;
    GLsizei     count;
    GLchar**    string;
    GLint*      length;
} shaderlistItem;

unsigned int    live_shaders(0);
size_t          shaderlist_size(0);
shaderlistItem  *shaderlist(NULL);

extern "C" void storenewshader(GLenum type, GLuint _result)
{
    unsigned c;

    if (shaderlist_size <= live_shaders+1)
    {
        void* newshaderlist = realloc((void*)shaderlist,
                                    (shaderlist_size+growsize)
                                    *sizeof(shaderlistItem));
        if (!newshaderlist) {
            os::log("apitrace: warning: realloc at storenewshader failed\n");
            return;
        }
        shaderlist = (shaderlistItem*)newshaderlist;
        shaderlist_size += growsize;
    }

    for (c = 0; c < live_shaders; c++) {
        if (shaderlist[c].shader == _result) {
            break;
        }
    }
    if (shaderlist[c].shader != _result && _result != 0) {
        shaderlist[live_shaders].shader = _result;
        shaderlist[live_shaders].type = type;
        shaderlist[live_shaders].already_saved = false;
        shaderlist[live_shaders].count = 0;
        shaderlist[live_shaders].string = NULL;
        shaderlist[live_shaders].length = NULL;
        live_shaders++;
    }
}

extern "C" void storeshadersource(GLuint shader, GLsizei count,
                                  const GLchar * const * string,
                                  const GLint *length)
{
    unsigned        c;
    shaderlistItem* currentShader;

    /*
     * find our shader or make new if everything failed.
     * though, should not be need to make new shader instance
     * here (I think)
     */
    for (c = 0; c < live_shaders; c++) {
        if (shaderlist[c].shader == shader) {
            if(shaderlist[c].string != NULL) {
                for (unsigned i = 0; i < shaderlist[c].count; i++)
                    free(shaderlist[c].string[i]);
            }
            free(shaderlist[c].string);
            free(shaderlist[c].length);
            break;
        }
    }
    if (shaderlist[c].shader != shader && shader != 0) {
        shaderlist[live_shaders].shader = shader;
        shaderlist[live_shaders].already_saved = false;
        shaderlist[live_shaders].count = 0;
        shaderlist[live_shaders].string = NULL;
        shaderlist[live_shaders].length = NULL;
        c =  live_shaders++;
    }

    currentShader = &shaderlist[c];
    currentShader->count = count;

    if (length != NULL) {
        currentShader->length = (GLint*)malloc(currentShader->count
                                               *sizeof(GLint*));
    }

    currentShader->string = (GLchar**)malloc(sizeof(GLchar*)*
                                             currentShader->count);
    if (currentShader->string == NULL) {
        os::log("apitrace: warning: malloc at storeshadersource failed\n");
        return;
    }

    for (c = 0; c < count; c++)
    {
        unsigned thisLength(0);

        if (length != NULL)
            thisLength = length[c];

        if (thisLength == 0)
            thisLength = strlen(string[c])+1;

        if (currentShader->length != NULL)
            currentShader->length[c] = thisLength;

        currentShader->string[c] = (GLchar*)malloc(thisLength);
        if (currentShader->string[c] == NULL) {
            /*
             * return here is not really safe but at least report
             * what happened!
             */
            os::log("apitrace: warning: malloc at storeshadersource failed\n");
            return;
        }
        memcpy(currentShader->string[c], string[c], thisLength);
    }
}

extern "C" void removeshader(GLuint shader)
{

}

void fakeglCreateShader(GLenum type, GLuint name) {
    unsigned _call = trace::localWriter.beginEnter(&_glCreateShader_sig);
    trace::localWriter.beginArg(0);
    trace::localWriter.writeEnum(&_enumGLenum_sig, type);
    trace::localWriter.endArg();
    trace::localWriter.endEnter();
    trace::localWriter.beginLeave(_call);
    trace::localWriter.beginReturn();
    trace::localWriter.writeUInt(name);
    trace::localWriter.endReturn();
    trace::localWriter.endLeave();
}

void fakeglShaderSource(GLuint shader, GLsizei count,
                        const GLchar * const * string,
                        const GLint * length)
{
    unsigned _call = trace::localWriter.beginEnter(&_glShaderSource_sig);
    trace::localWriter.beginArg(0);
    trace::localWriter.writeUInt(shader);
    trace::localWriter.endArg();
    trace::localWriter.beginArg(1);
    trace::localWriter.writeSInt(count);
    trace::localWriter.endArg();
    trace::localWriter.beginArg(2);

    if (string) {
        size_t _cCconstGLchar1 = count > 0 ? count : 0;
        trace::localWriter.beginArray(_cCconstGLchar1);
        for (size_t _iCconstGLchar1 = 0; _iCconstGLchar1 < _cCconstGLchar1;
             ++_iCconstGLchar1) {

            trace::localWriter.beginElement();
            trace::localWriter.writeString(
                    reinterpret_cast<const char *>((string)[_iCconstGLchar1]),
                        _glShaderSource_length(string, length,
                                               _iCconstGLchar1));

            trace::localWriter.endElement();
        }
        trace::localWriter.endArray();
    } else {
        trace::localWriter.writeNull();
    }
    trace::localWriter.endArg();
    trace::localWriter.beginArg(3);

    if (length) {
        size_t _cCGLint34 = count > 0 ? count : 0;
        trace::localWriter.beginArray(_cCGLint34);

        for (size_t _iCGLint34 = 0; _iCGLint34 < _cCGLint34; ++_iCGLint34) {
            trace::localWriter.beginElement();
            trace::localWriter.writeSInt((length)[_iCGLint34]);
            trace::localWriter.endElement();
        }
        trace::localWriter.endArray();
    } else {
        trace::localWriter.writeNull();
    }

    trace::localWriter.endArg();
    trace::localWriter.endEnter();

    trace::localWriter.beginLeave(_call);
    trace::localWriter.endLeave();
}

void fakeglCreateProgram(GLuint name) {
    unsigned _call = trace::localWriter.beginEnter(&_glCreateProgram_sig);
    trace::localWriter.endEnter();
    trace::localWriter.beginLeave(_call);
    trace::localWriter.beginReturn();
    trace::localWriter.writeUInt(name);
    trace::localWriter.endReturn();
    trace::localWriter.endLeave();
}

typedef struct progAttrib {
    struct progAttrib*  next;
    GLint               index;
    GLchar*             name;
} progAttrib;

typedef struct {
    GLint       program;
    progAttrib* attribLL;
} proglistItem;

unsigned int live_programs(0);
size_t       programlist_size(0);
proglistItem *programlist(NULL);

extern "C" void storenewprogram(const GLuint program)
{
    if (programlist_size <= live_programs+1)
    {
        void* new_programlist = realloc((void*)programlist,
                                    (programlist_size+growsize)
                                    *sizeof(proglistItem));
        if (!new_programlist) {
            os::log("apitrace: warning: realloc at storenewprogram failed\n");
            return;
        }
        programlist = (proglistItem*)new_programlist;
        programlist_size += growsize;
    }

    unsigned c;

    for (c = 0; c < live_programs; c++) {
        if (programlist[c].program == program) {
            break;
        }
    }
    if (programlist[c].program != program && program != 0) {
        programlist[live_programs].program = program;
        programlist[live_programs].attribLL = (progAttrib*)NULL;
        live_programs++;
    }
}

void fakeglBindAttribLocation(GLuint program, GLuint index,
                              const GLchar * name)
{
    unsigned _call = trace::localWriter.beginEnter(&_glBindAttribLocation_sig);
    trace::localWriter.beginArg(0);
    trace::localWriter.writeUInt(program);
    trace::localWriter.endArg();
    trace::localWriter.beginArg(1);
    trace::localWriter.writeUInt(index);
    trace::localWriter.endArg();
    trace::localWriter.beginArg(2);
    trace::localWriter.writeString(reinterpret_cast<const char *>(name));
    trace::localWriter.endArg();
    trace::localWriter.endEnter();
    trace::localWriter.beginLeave(_call);
    trace::localWriter.endLeave();
}

extern "C" void storeboundattrib(const GLuint program, GLuint index,
                                 const GLchar * name)
{
    unsigned    c;
    progAttrib** cAttrib;

    for (c = 0; c <live_programs; c++) {

        if (programlist[c].program == program)
            break;
    }

    if (programlist[c].program == program && program != 0) {
        for (cAttrib = &(programlist[c].attribLL); *cAttrib != NULL;
             cAttrib = &((**cAttrib).next)) {
            /*
             * get one block which also has space for the name in it
             */
            *cAttrib = (progAttrib*)calloc(1, sizeof(progAttrib)
                                               + strlen(name)+1);
            (*cAttrib)->index = index;
            (*cAttrib)->name = ((GLchar*)(*cAttrib))+sizeof(progAttrib);
            memcpy((void*)(*cAttrib)->name, (void*)name, strlen(name));
        }
    }
}


extern "C" void removeprogram(const GLuint program)
{
    unsigned c2, s;

    for (c2 = 0, s = 0; c2+s < live_programs; c2++) {
        if (programlist[c2].program == program) {
            for (progAttrib* attrib = programlist[c2].attribLL;
                 attrib != NULL;) {

                progAttrib* attribtemp = attrib;
                attrib = attrib->next;
                free((void*)attribtemp);
            }
            s++;
        }

        if (s > 0) {
            memcpy((void*)(&programlist[c2]), (void*)(&programlist[c2+s]),
                           sizeof(proglistItem));
        }
    }
    live_programs -= s;
}


/*
 * For rebuilding gl state in single frame capture mode.
 */
extern "C" void stateRebuild(void)
{
    /*
     * viewport set always
     */
    GLint viewPort[4];
    _glGetIntegerv(GL_VIEWPORT, (GLint*)&viewPort);
    glViewport(viewPort[0], viewPort[1], viewPort[2], viewPort[3]);

    GLint scissorBox[4];
    _glGetIntegerv(GL_SCISSOR_BOX, (GLint*)&scissorBox);
    if (memcmp((void*)&viewPort, (void*)&scissorBox, sizeof(viewPort)) != 0)
        glScissor(scissorBox[0], scissorBox[1], scissorBox[2], scissorBox[3]);

    /*
     * Enable/Disable parameters
     */
    const struct {
        GLenum param;
        void(*enabler)(GLenum);
    } simpleParams[] = {
        {GL_ALPHA_TEST, glEnable},
        {GL_AUTO_NORMAL, glEnable},
        {GL_BLEND, glEnable},
        {GL_COLOR_LOGIC_OP, glEnable},
        {GL_COLOR_MATERIAL, glEnable},
        {GL_COLOR_SUM, glEnable},
        {GL_COLOR_TABLE, glEnable},
        {GL_CONVOLUTION_1D, glEnable},
        {GL_CONVOLUTION_2D, glEnable},
        {GL_CULL_FACE, glEnable},
        {GL_DEPTH_TEST, glEnable},
        {GL_FOG, glEnable},
        {GL_HISTOGRAM, glEnable},
        {GL_INDEX_LOGIC_OP, glEnable},
        {GL_LIGHTING, glEnable},
        {GL_LINE_SMOOTH, glEnable},
        {GL_LINE_STIPPLE, glEnable},
        {GL_LOGIC_OP, glEnable},
        {GL_MAP1_COLOR_4, glEnable},
        {GL_MAP1_INDEX, glEnable},
        {GL_MAP1_NORMAL, glEnable},
        {GL_MAP1_TEXTURE_COORD_1, glEnable},
        {GL_MAP1_TEXTURE_COORD_2, glEnable},
        {GL_MAP1_TEXTURE_COORD_3, glEnable},
        {GL_MAP1_TEXTURE_COORD_4, glEnable},
        {GL_MAP1_VERTEX_3, glEnable},
        {GL_MAP1_VERTEX_4, glEnable},
        {GL_MAP2_COLOR_4, glEnable},
        {GL_MAP2_INDEX, glEnable},
        {GL_MAP2_NORMAL, glEnable},
        {GL_MAP2_TEXTURE_COORD_1, glEnable},
        {GL_MAP2_TEXTURE_COORD_2, glEnable},
        {GL_MAP2_TEXTURE_COORD_3, glEnable},
        {GL_MAP2_TEXTURE_COORD_4, glEnable},
        {GL_MAP2_VERTEX_3, glEnable},
        {GL_MAP2_VERTEX_4, glEnable},
        {GL_MINMAX, glEnable},
        {GL_NORMALIZE, glEnable},
        {GL_POINT_SMOOTH, glEnable},
        {GL_POINT_SPRITE, glEnable},
        {GL_POLYGON_OFFSET_FILL, glEnable},
        {GL_POLYGON_OFFSET_LINE, glEnable},
        {GL_POLYGON_OFFSET_POINT, glEnable},
        {GL_POLYGON_SMOOTH, glEnable},
        {GL_POLYGON_STIPPLE, glEnable},
        {GL_POST_COLOR_MATRIX_COLOR_TABLE, glEnable},
        {GL_POST_CONVOLUTION_COLOR_TABLE, glEnable},
        {GL_RESCALE_NORMAL, glEnable},
        {GL_SAMPLE_ALPHA_TO_COVERAGE, glEnable},
        {GL_SAMPLE_ALPHA_TO_ONE, glEnable},
        {GL_SAMPLE_COVERAGE, glEnable},
        {GL_SEPARABLE_2D, glEnable},
        {GL_SCISSOR_TEST, glEnable},
        {GL_STENCIL_TEST, glEnable},
        {GL_TEXTURE_1D, glEnable},
        {GL_TEXTURE_2D, glEnable},
        {GL_TEXTURE_3D, glEnable},
        {GL_TEXTURE_CUBE_MAP, glEnable},
        {GL_TEXTURE_GEN_Q, glEnable},
        {GL_TEXTURE_GEN_R, glEnable},
        {GL_TEXTURE_GEN_S, glEnable},
        {GL_TEXTURE_GEN_T, glEnable},
        {GL_VERTEX_PROGRAM_POINT_SIZE, glEnable},
        {GL_VERTEX_PROGRAM_TWO_SIDE, glEnable},

        {GL_COLOR_ARRAY, glEnableClientState },
        {GL_EDGE_FLAG_ARRAY, glEnableClientState },
        {GL_FOG_COORD_ARRAY, glEnableClientState },
        {GL_INDEX_ARRAY, glEnableClientState },
        {GL_NORMAL_ARRAY, glEnableClientState },
        {GL_SECONDARY_COLOR_ARRAY, glEnableClientState },
        {GL_TEXTURE_COORD_ARRAY, glEnableClientState },
        {GL_VERTEX_ARRAY, glEnableClientState }
    };

    for (int c = 0; c < sizeof(simpleParams)/sizeof(simpleParams[0]); c++) {
        if (_glIsEnabled(simpleParams[c].param) == GL_TRUE) {
            simpleParams[c].enabler(simpleParams[c].param);
        }
    }

    /*
     * GL_DITHER and GL_MULTISAMPLE are enabled by default so we'll
     * check if they need to be disabled.
     */
    if (_glIsEnabled(GL_DITHER) == GL_FALSE)
        glDisable(GL_DITHER);

    if (_glIsEnabled(GL_MULTISAMPLE) == GL_FALSE)
        glDisable(GL_MULTISAMPLE);

    /*
     * Clip Planes
     */
    unsigned plane_max;
    _glGetIntegerv(GL_MAX_CLIP_PLANES, (GLint*)&plane_max);

    GLdouble clipPlaneRVals[4], clipPlaneDefault[4] = {0, 0, 0, 0};

    for (unsigned c = 0; c < plane_max; c++) {
        if (_glIsEnabled(GL_CLIP_PLANE0+c) == GL_TRUE)
            glEnable(GL_CLIP_PLANE0+c);

        _glGetClipPlane(GL_CLIP_PLANE0+c, (GLdouble*)&clipPlaneRVals);
        if (memcmp((void*)&clipPlaneRVals, (void*)&clipPlaneDefault,
                   sizeof(clipPlaneRVals)) != 0)
            glClipPlane(GL_CLIP_PLANE0+c, (GLdouble*)&clipPlaneRVals);
    }

    /*
     * Simple Lights
     */
    const struct {
        GLenum  lightType;
        int     paramAmount; /* max 4 */
        GLfloat params0[4];  /* light 0 special case */
        GLfloat paramsn[4];  /* other than 0 lights */
    } lightTypes[] = {
        { GL_AMBIENT, 4, {0, 0, 0, 1}, {0, 0, 0, 1} },
        { GL_DIFFUSE, 4, {1, 1, 1, 1}, {0, 0, 0, 1} },
        { GL_SPECULAR, 4, {1, 1, 1, 1}, {0, 0, 0, 1} },
        { GL_POSITION, 4, {0, 0, 1, 0}, {0, 0, 1, 0} },
        { GL_SPOT_DIRECTION, 3, {0, 0, -1, 0}, {0, 0, -1, 0} },
        { GL_SPOT_EXPONENT, 1, {0, 0, 0, 0}, {0, 0, 0, 0} },
        { GL_SPOT_CUTOFF, 1, {180, 0, 0, 0}, {180, 0, 0, 0} },
        { GL_CONSTANT_ATTENUATION, 1, {1, 0, 0, 0}, {1, 0, 0, 0} },
        { GL_LINEAR_ATTENUATION, 1, {0, 0, 0, 0}, {0, 0, 0, 0} },
        { GL_QUADRATIC_ATTENUATION, 1, {0, 0, 0, 0}, {0, 0, 0, 0} }
    };

    unsigned c_max;
    _glGetIntegerv(GL_MAX_LIGHTS, (GLint*)&c_max);

    for (unsigned c = 0; c < c_max; c++) {
        if (_glIsEnabled(GL_LIGHT0+c) == GL_TRUE)
            glEnable(GL_LIGHT0+c);

        GLfloat lightRVals[4];

        for (unsigned c2 = 0; c2 < sizeof(lightTypes)/sizeof(lightTypes[0]);
             c2++) {

            _glGetLightfv(GL_LIGHT0+c, lightTypes[c2].lightType,
                         (GLfloat*)&lightRVals );

            /*
             * light 0 special case
             */
            if (c == 0) {
                if (memcmp((void*)&lightRVals, (void*)&lightTypes[c2].params0,
                           sizeof(GLfloat)*lightTypes[c2].paramAmount) != 0)
                    glLightfv(GL_LIGHT0,lightTypes[c2].lightType,
                              (GLfloat*)&lightRVals );
            }
            else {
                if (memcmp((void*)&lightRVals, (void*)&lightTypes[c2].paramsn,
                           sizeof(GLfloat)*lightTypes[c2].paramAmount) != 0)
                    glLightfv(GL_LIGHT0+c,lightTypes[c2].lightType,
                              (GLfloat*)&lightRVals );
            }
        }
    }

    /*
     * matrixes
     */
    GLint matrixMode, matrixMode2; /* will be used to set final matrix mode */
    GLfloat matrix[16];
    const GLfloat iMatrix[16] = {1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1};
    const struct {
        GLenum matrixname;
        GLenum modename;
        GLenum stackdepth;
    } matrixList[] = {
        { GL_PROJECTION_MATRIX, GL_PROJECTION, GL_PROJECTION_STACK_DEPTH },
        { GL_TEXTURE_MATRIX, GL_TEXTURE, GL_TEXTURE_STACK_DEPTH },
        { GL_COLOR_MATRIX, GL_COLOR, GL_COLOR_MATRIX_STACK_DEPTH },
        { GL_MODELVIEW_MATRIX, GL_MODELVIEW, GL_MODELVIEW_STACK_DEPTH }
    };

    _glGetIntegerv(GL_MATRIX_MODE, (GLint*)&matrixMode);
    matrixMode2 = matrixMode;

    /*
     * FIXME
     * matrix stack is not handled for now, its depth should be asked with
     * matrixlist.stacdepth and popped/pushed back'n'forth
     * -> Then again, how many applications have stuff in matrix stack
     * between frames?
     */
    for (unsigned c = 0; c < sizeof(matrixList)/sizeof(matrixList[0]); c++) {
        _glGetFloatv(matrixList[c].matrixname, (GLfloat*)&matrix);
        if (memcmp((void*)&iMatrix, (void*)&matrix, sizeof(matrix)) != 0) {
             glMatrixMode(matrixList[c].modename);
             matrixMode2 = matrixList[c].modename;
            glLoadMatrixf((GLfloat*)&matrix);
        }
    }

    if (matrixMode != matrixMode2)
        glMatrixMode(matrixMode);

    const GLfloat onef(1.0f), zerof(0.0f);
#define max_multiparam 4
    const struct {
        GLenum   parameter[max_multiparam];
        GLenum   defaultVal[max_multiparam];
        unsigned paramAmount; /* max 4. extend fps struct if needed */
        struct fps {
            fps(void (*f1)(GLenum)) : oneparam(f1){}
            fps(void (*f2)(GLenum, GLenum)) : twoparam(f2){}
            fps(void (*f2_2)(GLenum, GLint)) : twoparam_2(f2_2){}
            fps(void (*f4)(GLfloat, GLfloat, GLfloat, GLfloat)) :
                fourparam(f4){}
            fps(void (*f5)(GLenum, GLfloat, GLfloat, GLfloat, GLfloat)) :
                fourparam_2(f5){}
            union {
                void(*oneparam)(GLenum);
                void(*twoparam)(GLenum, GLenum);
                void(*twoparam_2)(GLenum, GLint);
                void(*fourparam)(GLfloat, GLfloat, GLfloat, GLfloat);
                void(*fourparam_2)(GLenum, GLfloat, GLfloat, GLfloat, GLfloat);
            };
        } f;
    } multiParamList[] = {
        {{GL_CULL_FACE_MODE}, {GL_BACK}, 1, {glCullFace}},
        {{GL_DEPTH_FUNC}, {GL_LESS}, 1, {glDepthFunc}},
        {{GL_FOG_HINT}, {GL_DONT_CARE}, 1, {glHint}},
        {{GL_GENERATE_MIPMAP_HINT}, {GL_DONT_CARE}, 1, {glHint}},
        {{GL_LINE_SMOOTH_HINT}, {GL_DONT_CARE}, 1, {glHint}},
        {{GL_LINE_SMOOTH_HINT}, {GL_DONT_CARE}, 1, {glHint}},
        {{GL_PERSPECTIVE_CORRECTION_HINT}, {GL_DONT_CARE}, 1, {glHint}},
        {{GL_POINT_SMOOTH_HINT}, {GL_DONT_CARE}, 1, {glHint}},
        {{GL_POLYGON_SMOOTH_HINT}, {GL_DONT_CARE}, 1, {glHint}},
        {{GL_TEXTURE_COMPRESSION_HINT}, {GL_DONT_CARE}, 1, {glHint}},
        {{GL_FRAGMENT_SHADER_DERIVATIVE_HINT}, {GL_DONT_CARE}, 1, {glHint}},
        {{GL_PACK_ALIGNMENT}, {4}, 1, {glPixelStorei}},
        {{GL_UNPACK_ALIGNMENT}, {4}, 1, {glPixelStorei}},

        {{GL_BLEND_SRC_RGB,GL_BLEND_DST_RGB}, {GL_ONE,GL_ZERO}, 2,
            {glBlendFunc}},

        {{GL_CURRENT_TEXTURE_COORDS}, {*(GLenum*)&zerof, *(GLenum*)&zerof,
                *(GLenum*)&zerof, *(GLenum*)&onef}, 4, {glMultiTexCoord4f}},
        {{GL_COLOR_CLEAR_VALUE}, {*(GLenum*)&zerof, *(GLenum*)&zerof,
                *(GLenum*)&zerof, *(GLenum*)&zerof}, 4, {glClearColor}}
    };

    for (unsigned c = 0; c < sizeof(multiParamList)/sizeof(multiParamList[0]);
         c++) {

        GLint   rVal[max_multiparam];
        GLfloat* rValf = (GLfloat*)&rVal;
        GLenum err(GL_NO_ERROR);

        for (unsigned c2 = 0; c2 < multiParamList[c].paramAmount &&
             err == GL_NO_ERROR; c2++, err = _glGetError() ) {

            if (multiParamList[c].paramAmount == 4) {
                _glGetFloatv(multiParamList[c].parameter[c2],
                             (GLfloat*)&rVal[c2]);
                c2 += 4;
            }
            else {
                _glGetIntegerv(multiParamList[c].parameter[c2],
                               (GLint*)&rVal[c2]);
            }
        }

        if (err == GL_NO_ERROR && memcmp((void*)
            &multiParamList[c].defaultVal,(void*)&rVal,
            sizeof(GLint)*multiParamList[c].paramAmount) != 0) {

            switch (multiParamList[c].paramAmount) {
            default:
                assert(!"unreachable!");
                break;
            case 1:
                if (multiParamList[c].f.twoparam == glHint ||
                    multiParamList[c].f.twoparam_2 == glPixelStorei) {
                    multiParamList[c].f.twoparam(
                                multiParamList[c].parameter[0], rVal[0]);
                }
                else {
                    multiParamList[c].f.oneparam(rVal[0]);
                }
                break;
            case 2:
                multiParamList[c].f.twoparam(rVal[0], rVal[1]);
                break;
            case 4:
                if (multiParamList[c].parameter[0] ==
                        GL_CURRENT_TEXTURE_COORDS) {
                    /*
                     * FIXME:
                     * query texture to use here!
                     */
                    glMultiTexCoord4f(GL_TEXTURE0, rValf[0], rValf[1],
                                                   rValf[2], rValf[3]);
                }
                else {
                    multiParamList[c].f.fourparam(rValf[0], rValf[1],
                                                  rValf[2], rValf[3]);
                }
                break;
            }
        }
    }

    /*
     * textures
     */

    /*
     * store texture bindings before continue with anything
     */
    GLuint activeTexture(0), maxTexUnit(0);
    const GLenum texturebinding[] = {GL_TEXTURE_BINDING_1D,
            GL_TEXTURE_BINDING_1D_ARRAY, GL_TEXTURE_BINDING_2D,
            GL_TEXTURE_BINDING_2D_ARRAY, GL_TEXTURE_BINDING_2D_MULTISAMPLE,
            GL_TEXTURE_BINDING_2D_MULTISAMPLE_ARRAY, GL_TEXTURE_BINDING_3D,
            GL_TEXTURE_BINDING_BUFFER, GL_TEXTURE_BINDING_CUBE_MAP,
            GL_TEXTURE_BINDING_RECTANGLE };

    const GLenum textureEnabled[] = {GL_TEXTURE_1D, GL_TEXTURE_2D,
                                     GL_TEXTURE_3D };

    _glGetIntegerv(GL_ACTIVE_TEXTURE , (GLint*)&activeTexture);
    _glGetIntegerv(GL_MAX_TEXTURE_UNITS, (GLint*)&maxTexUnit);

    GLenum storedTextureBindings[maxTexUnit][sizeof(texturebinding)/
            sizeof(texturebinding[0])];

    GLenum storedTextureEnabled[maxTexUnit][sizeof(textureEnabled)/
            sizeof(textureEnabled[0])];

    for (unsigned c = 0; c < sizeof(maxTexUnit); c++) {
        _glActiveTexture(GL_TEXTURE0+c);

        for (unsigned c2 = 0; c2  < sizeof(texturebinding)/
             sizeof(texturebinding[0]); c2++ ) {
            _glGetIntegerv(texturebinding[c2],
                           (GLint*)&storedTextureBindings[c][c2]);
            if (_glGetError() != GL_NO_ERROR)
                storedTextureBindings[c][c2] = 0;
        }

        for (unsigned c2 = 0; c2  < sizeof(textureEnabled)/
             sizeof(textureEnabled[0]); c2++ ) {

            _glGetIntegerv(textureEnabled[c2],
                           (GLint*)&storedTextureEnabled[c][c2]);

            if (_glGetError() != GL_NO_ERROR)
                storedTextureEnabled[c][c2] = 0;
        }
    }

    int bytes(0);
    GLubyte* pixels(NULL);

    const struct {
        GLenum texParam;
        GLint  pDefault;
    } texParams[] = {
        {GL_DEPTH_STENCIL_TEXTURE_MODE, GL_DEPTH_COMPONENT},
        {GL_TEXTURE_MAG_FILTER, GL_LINEAR},
        {GL_TEXTURE_MIN_FILTER, GL_NEAREST_MIPMAP_LINEAR},
        {GL_TEXTURE_MIN_LOD, -1000},
        {GL_TEXTURE_MAX_LOD, 1000},
        {GL_TEXTURE_BASE_LEVEL, 0},
/*        {GL_TEXTURE_MAX_LEVEL, 1000},*/
        {GL_TEXTURE_SWIZZLE_R, GL_RED},
        {GL_TEXTURE_SWIZZLE_G, GL_GREEN},
        {GL_TEXTURE_SWIZZLE_B, GL_BLUE},
        {GL_TEXTURE_SWIZZLE_A, GL_ALPHA},
        {GL_TEXTURE_WRAP_S, GL_REPEAT},
        {GL_TEXTURE_WRAP_T, GL_REPEAT},
        {GL_TEXTURE_WRAP_R, GL_REPEAT},
        {GL_TEXTURE_PRIORITY, 1},
        {GL_TEXTURE_COMPARE_MODE, GL_NONE },
        {GL_TEXTURE_COMPARE_FUNC, GL_LEQUAL },
        {GL_DEPTH_TEXTURE_MODE, GL_LUMINANCE },
        {GL_GENERATE_MIPMAP, GL_FALSE }
    };

//    {GL_TEXTURE_BORDER_COLOR,

    for (unsigned c = 0; c < live_textures; c++) {
        if (texturelist[c].already_saved == true)
            continue;
        /*
         * write glGenTextures just to trace but
         * not call actual glGenTextures function.
         */
        fakeglGenTextture(texturelist[c].texture);

        glBindTexture(GL_TEXTURE_2D, texturelist[c].texture);

        for (unsigned c2 = 0; c2 < sizeof(texParams)/sizeof(texParams[0]);
             c2++ ) {

            GLint texRVal;

            _glGetTexParameteriv(GL_TEXTURE_2D, texParams[c2].texParam,
                                 (GLint*)&texRVal);

            if (texRVal != texParams[c2].pDefault &&
                    glGetError() == GL_NO_ERROR) {
                glTexParameteri(GL_TEXTURE_2D, texParams[c2].texParam,
                                texRVal);
            }
        }

        typedef struct {
            GLenum texParam;
            GLint  pDefault;
            GLint received;
        } texParamsglGet;

        struct {
            GLenum         pname;
            unsigned       pAmount;
            texParamsglGet params[8];
            GLvoid         *received;
        } texParamsArrays[] = {
        {GL_TEXTURE_COORD_ARRAY_POINTER, 3,
            {{GL_TEXTURE_COORD_ARRAY_SIZE, 4},
             {GL_TEXTURE_COORD_ARRAY_TYPE, GL_FLOAT},
             {GL_TEXTURE_COORD_ARRAY_STRIDE, 0}
            }},

        {GL_COLOR_ARRAY_POINTER, 3,
            {{GL_COLOR_ARRAY_SIZE, 4},
             {GL_COLOR_ARRAY_TYPE, GL_FLOAT},
             {GL_COLOR_ARRAY_STRIDE, 0}
            }},

        {GL_EDGE_FLAG_ARRAY_POINTER, 0},
        {GL_FOG_COORD_ARRAY_POINTER, 0},
        {GL_FEEDBACK_BUFFER_POINTER, 0},
        {GL_INDEX_ARRAY_POINTER, 0},
        {GL_NORMAL_ARRAY_POINTER, 0},
        {GL_SECONDARY_COLOR_ARRAY_POINTER, 0},
        {GL_SELECTION_BUFFER_POINTER, 0},

        {GL_VERTEX_ARRAY_POINTER, 3,
            {{GL_VERTEX_ARRAY_SIZE, 4},
             {GL_VERTEX_ARRAY_TYPE, GL_FLOAT},
             {GL_VERTEX_ARRAY_STRIDE, 0}
            }}
        };

        for (unsigned c2 = 0; c2 < sizeof(texParamsArrays)/
             sizeof(texParamsArrays[0]); c2++ ) {

            _glGetPointerv(texParamsArrays[c2].pname,
                          (GLvoid**)&texParamsArrays[c2].received);

            if (_glGetError() != GL_NO_ERROR)
                texParamsArrays[c2].received = NULL;

            /*
             * such array in use?
             */
            if (texParamsArrays[c2].received == NULL)
                continue;

            for (unsigned c3 = 0; c3 < texParamsArrays[c2].pAmount; c3++ ) {

                _glGetIntegerv(texParamsArrays[c2].params[c3].texParam,
                            (GLint*)&texParamsArrays[c2].params[c3].received);

                if (_glGetError() != GL_NO_ERROR)
                    texParamsArrays[c2].params[c3].received =
                            texParamsArrays[c2].params[c3].pDefault;
            }

            switch (texParamsArrays[c2].pname) {
            default:
                break;
            case GL_TEXTURE_COORD_ARRAY_POINTER:
                glTexCoordPointer(
                            texParamsArrays[c2].params[0].received,
                            texParamsArrays[c2].params[1].received,
                            texParamsArrays[c2].params[2].received,
                            texParamsArrays[c2].received);
                break;
            case GL_COLOR_ARRAY_POINTER:
                glColorPointer(
                            texParamsArrays[c2].params[0].received,
                            texParamsArrays[c2].params[1].received,
                            texParamsArrays[c2].params[2].received,
                            texParamsArrays[c2].received);
                break;
            case GL_EDGE_FLAG_ARRAY_POINTER:
                break;
            case GL_FOG_COORD_ARRAY_POINTER:
                break;
            case GL_FEEDBACK_BUFFER_POINTER:
                break;
            case GL_INDEX_ARRAY_POINTER:
                break;
            case GL_NORMAL_ARRAY_POINTER:
                break;
            case GL_SECONDARY_COLOR_ARRAY_POINTER:
                break;
            case GL_SELECTION_BUFFER_POINTER:
                break;
            case GL_VERTEX_ARRAY_POINTER:
                glVertexPointer(
                            texParamsArrays[c2].params[0].received,
                            texParamsArrays[c2].params[1].received,
                            texParamsArrays[c2].params[2].received,
                            texParamsArrays[c2].received);
                break;
            }
        }

        GLint textureMaxLevel;

        _glGetTexParameteriv(GL_TEXTURE_2D, GL_TEXTURE_MAX_LEVEL,
                             &textureMaxLevel);

        for( unsigned c2 = 0; c2 < textureMaxLevel; c2++ ) {
            GLint textureWidth;

            _glGetTexLevelParameteriv(GL_TEXTURE_2D, c2, GL_TEXTURE_WIDTH,
                                      &textureWidth);
            /*
             * Different gl implementations report differently if there was
             * no more texture level available.
             */
            if (textureWidth == 0 || _glGetError() != GL_NO_ERROR)
                break;

            GLint textureHeight, textureDepth, textureIFormat;

            _glGetTexLevelParameteriv(GL_TEXTURE_2D, c2, GL_TEXTURE_HEIGHT,
                &textureHeight);

            _glGetTexLevelParameteriv(GL_TEXTURE_2D, c2, GL_TEXTURE_DEPTH,
                &textureDepth);

            _glGetTexLevelParameteriv(GL_TEXTURE_2D, c2,
                GL_TEXTURE_INTERNAL_FORMAT, &textureIFormat);

            /*
             * FIXME:
             * Cannot get compressed textures, need to play with them
             * differently. Hardcode GL_RGBA here for now.
             */
            textureIFormat = GL_RGBA;

            if (bytes < textureWidth*textureHeight*4)
            {
                bytes = textureWidth*textureHeight*4;
                pixels = (GLubyte*)realloc(pixels,bytes);
            }

            _glGetTexImage(GL_TEXTURE_2D,c2, textureIFormat,GL_UNSIGNED_BYTE,
                pixels);

            fakeglTexImage2D(GL_TEXTURE_2D, c2, textureIFormat, textureWidth,
                textureHeight, 0, textureIFormat, GL_UNSIGNED_BYTE,
                (GLvoid*)pixels);
        }

        texturelist[c].already_saved = true;
    }
    free(pixels);

    /*
     *  Restore texture bindings
     */
    for (unsigned c = 0; c < sizeof(maxTexUnit); c++) {

        unsigned setUnit;

        if (c == 0)
            setUnit = 1;
        else
            setUnit = 0;

        for (unsigned c2 = 0; c2  < sizeof(texturebinding)/
             sizeof(texturebinding[0]); c2++ )
            if (storedTextureBindings[c][c2] != 0) {

                if (setUnit == 0) {
                    glActiveTexture(GL_TEXTURE0+c);
                }

                glBindTexture(GL_TEXTURE_2D,
                              storedTextureBindings[c][c2]);
                setUnit++;
            }

        for (unsigned c2 = 0; c2  < sizeof(textureEnabled)/
             sizeof(textureEnabled[0]); c2++ )
            if (storedTextureEnabled[c][c2] == GL_TRUE) {
                glActiveTexture(GL_TEXTURE0+c);

                glEnable(textureEnabled[c2]);
                setUnit++;
            }
    }

    if (activeTexture != GL_TEXTURE0)
        glActiveTexture(activeTexture);
    else
        _glActiveTexture(activeTexture);


    /*
     * programs, shaders, uniforms.
     */
    GLint current_program(0);

    _glGetIntegerv(GL_CURRENT_PROGRAM, &current_program);


    for (unsigned c = 0; c < live_shaders; c++) {
        fakeglCreateShader(shaderlist[c].type, shaderlist[c].shader);
        fakeglShaderSource(shaderlist[c].shader, shaderlist[c].count,
                           shaderlist[c].string, shaderlist[c].length);
        glCompileShader(shaderlist[c].shader);
    }

    GLint   aShaderListSize(0);
    GLuint* aShaderList(NULL);

    for (unsigned c = 0; c < live_programs; c++) {
        fakeglCreateProgram(programlist[c].program);

        GLint   attachedShaders(0), shCount(0);

        _glGetProgramiv(programlist[c].program, GL_ATTACHED_SHADERS,
                        &attachedShaders);

        if (aShaderListSize < attachedShaders) {
            void* newlist = realloc(aShaderList,
                                    attachedShaders*sizeof(GLint));
            if (newlist == NULL) {
                os::log("apitrace: warning: realloc at staterebuild failed\n");
                continue;
            }
            aShaderList = (GLuint*)newlist;
        }

        _glGetAttachedShaders(programlist[c].program, attachedShaders,
                              &shCount, aShaderList );

        for (unsigned c2 = 0; c2 < shCount; c2++) {
            /*
             * This ought to cause boat load of GL_INVALID_OPERATION
             * errors because these shaders are already attached here,
             * just ignore the errors because this is something we want
             * to end up into the trace file.
             */
            glAttachShader(programlist[c].program, aShaderList[c2]);
        }

        for (progAttrib* attrib = programlist[c].attribLL; attrib != NULL;
             attrib = attrib->next) {
            fakeglBindAttribLocation(programlist[c].program, attrib->index,
                                     attrib->name);
        }
        glLinkProgram(programlist[c].program);


    }
    free ((void*)aShaderList);

    if (current_program != 0)
        glUseProgram(current_program);

    return;
}

'''
