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

    return;
}

'''
