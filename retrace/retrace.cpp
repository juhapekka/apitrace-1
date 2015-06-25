/**************************************************************************
 *
 * Copyright 2011 Jose Fonseca
 * All Rights Reserved.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 *
 **************************************************************************/


#include <string.h>
#include <iostream>

#include "os_time.hpp"
#include "retrace.hpp"

#ifdef _WIN32
#include <dxerr.h>
#endif


namespace retrace {


trace::DumpFlags dumpFlags = trace::DUMP_FLAG_THREAD_IDS;
std::ofstream c_file;
std::ofstream c_file_tables;
std::ofstream c_file_includes;

static bool call_dumped = false;


static void dumpCall(trace::Call &call) {
    if (verbosity >= 0 && !call_dumped) {
        if(dumpFlags & trace::DUMP_FLAG_C_SOURCE) {
            trace::dump(call, c_file, c_file_tables, c_file_includes, dumpFlags);
        }
        else {
            trace::dump(call, std::cout, std::cout, std::cout, dumpFlags);
        }
        std::cout.flush();
        call_dumped = true;
    }
}


std::ostream &warning(trace::Call &call) {
    dumpCall(call);

    std::cerr << call.no << ": ";
    std::cerr << "warning: ";

    return std::cerr;
}


#ifdef _WIN32
void
failed(trace::Call &call, HRESULT hr)
{
    std::ostream &os = warning(call);

    os << "failed with 0x" << std::hex << hr << std::dec;

    LPCSTR lpszErrorString = DXGetErrorStringA(hr);
    assert(lpszErrorString);
    os << " (" << lpszErrorString << "): ";

    char szErrorDesc[512];
    DXGetErrorDescriptionA(hr, szErrorDesc, sizeof szErrorDesc);
    os << szErrorDesc;

    os << "\n";
}
#endif /* _WIN32 */


void
checkMismatch(trace::Call &call, const char *expr, trace::Value *traceValue, long actualValue)
{
    assert(traceValue);
    long traceIntValue = traceValue->toSInt();
    if (traceIntValue == actualValue) {
        return;
    }

    std::ostream &os = warning(call);
    os << "mismatch in " << expr << ": expected " << traceIntValue << " but got " << actualValue << "\n";
}


void ignore(trace::Call &call) {
    (void)call;
}

void unsupported(trace::Call &call) {
    warning(call) << "unsupported " << call.name() << " call\n";
}

inline void Retracer::addCallback(const Entry *entry) {
    assert(entry->name);
    assert(entry->callback);
    map[entry->name] = entry->callback;
}


void Retracer::addCallbacks(const Entry *entries) {
    while (entries->name && entries->callback) {
        addCallback(entries++);
    }
}

void Retracer::retrace(trace::Call &call) {
    call_dumped = false;
    bool dumpthis = true;

    Callback callback = 0;

    trace::Id id = call.sig->id;
    if (id >= callbacks.size()) {
        callbacks.resize(id + 1);
        callback = 0;
    } else {
        callback = callbacks[id];
    }

    if (!callback) {
        Map::const_iterator it = map.find(call.name());
        if (it == map.end()) {
            callback = &unsupported;
        } else {
            callback = it->second;
        }
        callbacks[id] = callback;
    }

    assert(callback);
    assert(callbacks[id] == callback);

    if (dumpFlags&trace::DUMP_FLAG_C_SOURCE) {
        static int headerswritten = 0;

        if (strncmp(call.name(), "egl", 3) == 0) {
            if (headerswritten == 0) {
                std::ofstream tempstream;
                char newname[1024];
                sprintf((char*)&newname, "%s/testmain.c",
                        retrace::c_source_folder);

                tempstream.open(newname);
                tempstream << egl_stub_main_source;
                tempstream.close();

                sprintf((char*)&newname, "%s/Makefile",
                        retrace::c_source_folder);
                tempstream.open(newname);
                tempstream << egl_makefile;
                tempstream.close();

                retrace::c_file_includes << "#include <GLES3/gl3.h>\n"
                                         << "#include <GLES3/gl3ext.h>\n"
                                         << "#include <EGL/egl.h>\n"
                                         << "#include <EGL/eglext.h>\n\n"
                                         << "extern EGLDisplay egl_display;\n"
                                         << "extern EGLContext egl_context;\n"
                                         << "extern EGLSurface egl_surface;\n\n"
                                         << "void frame_0();\n";
                headerswritten++;
            }

            if (strcmp(call.name(), "eglChooseConfig") == 0) {
                static int confnumber = 0;
                trace::Array *attrib_array = call.arg(1).toArray();
                retrace::c_file_includes << "extern int egl_config_params"<< std::dec
                                         << confnumber << "[];\n";
                retrace::c_file_tables << "int egl_config_params"<< std::dec
                                       << confnumber << "[] = { ";

                for (int c = 0; c < attrib_array->values.size(); c++) {
                    int param = attrib_array->values[c]->toSInt();
                    retrace::c_file_tables << std::dec << param << ", ";
                }
                retrace::c_file_tables << "0 };\n";
                confnumber++;
            }
            if (strcmp(call.name(), "eglBindAPI") == 0) {
                static int apinumber = 0;

                retrace::c_file_includes << "extern int egl_api_bind"<< std::dec
                                         << apinumber << ";\n";
                retrace::c_file_tables << "int egl_api_bind"<< std::dec
                                       << apinumber << " = 0x" << std::hex
                                       << call.arg(0).toUInt() << ";\n";
                apinumber++;
            }

            if (strcmp(call.name(), "eglCreateContext") == 0) {
                static int contextnumber = 0;
                trace::Array *attrib_array = call.arg(3).toArray();
                retrace::c_file_includes << "extern int egl_context_params"<< std::dec
                                         << contextnumber << "[];\n";
                retrace::c_file_tables << "int egl_context_params"<< std::dec
                                       << contextnumber << "[] = { ";

                for (int c = 0; c < attrib_array->values.size(); c++) {
                    int param = attrib_array->values[c]->toSInt();
                    retrace::c_file_tables << std::dec << param << ", ";
                }
                retrace::c_file_tables << "0 };\n";
                contextnumber++;
            }

            dumpthis = false;

            if (strcmp(call.name(), "eglSwapBuffers") == 0) {
                dumpthis = true;
            }
        }

        if (strncmp(call.name(), "glX", 3) == 0) {
            if (headerswritten == 0) {
                retrace::c_file_includes << "#include <GL/gl.h>\n"
                                         << "#include <GL/glx.h>\n"
                                         << "#include <GL/glu.h>\n"
                                         << "#include <GL/glext.h>\n\n"
                                         << "extern EGLDisplay egl_display;\n"
                                         << "extern EGLContext egl_context;\n"
                                         << "extern EGLSurface egl_surface;\n\n"
                                         << "void frame_0();\n";
                headerswritten++;
            }
        }
    }


    if (verbosity >= 1 && dumpthis) {
        if (verbosity >= 2 ||
            (!(call.flags & trace::CALL_FLAG_VERBOSE) &&
             callback != &ignore)) {
            dumpCall(call);
        }
    }

    callback(call);
}


} /* namespace retrace */
