/**************************************************************************
 *
 * Copyright 2011-2012 Jose Fonseca
 * Copyright (C) 2013 Intel Corporation. All rights reversed.
 * Author: Shuang He <shuang.he@intel.com>
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

#pragma once

#include <assert.h>
#include <string.h>

#include <list>
#include <map>
#include <ostream>
#include <fstream>

#ifdef _WIN32
#include <windows.h>
#endif

#include "trace_model.hpp"
#include "trace_parser.hpp"
#include "trace_profiler.hpp"
#include "trace_dump.hpp"

#include "scoped_allocator.hpp"


namespace image {
    class Image;
}

class StateWriter;


namespace retrace {


extern trace::Parser parser;
extern trace::Profiler profiler;


class ScopedAllocator : public ::ScopedAllocator
{
public:
    /**
     * Allocate an array with the same dimensions as the specified value.
     */
    inline void *
    allocArray(const trace::Value *value, size_t elemSize) {
        const trace::Array *array = value->toArray();
        if (array) {
            size_t numElems = array->size();
            size_t size = numElems * elemSize;
            void *ptr = ::ScopedAllocator::alloc(size);
            if (ptr) {
                memset(ptr, 0, size);
            }
            return ptr;
        }
        const trace::Null *null = value->toNull();
        if (null) {
            return NULL;
        }
        assert(0);
        return NULL;
    }

    /**
     * XXX: We must not compute sizeof(T) inside the function body! d3d8.h and
     * d3d9.h have declarations of D3DPRESENT_PARAMETERS and D3DVOLUME_DESC
     * structures with different size sizes.  Multiple specializations of these
     * will be produced (on debug builds, as on release builds the whole body
     * is inlined.), and the linker will pick up one, leading to wrong results
     * if the smallest specialization is picked.
     */
    template< class T >
    inline T *
    allocArray(const trace::Value *value, size_t sizeof_T = sizeof(T)) {
        return static_cast<T *>(allocArray(value, sizeof_T));
    }

};


/**
 * Output verbosity when retracing files.
 */
extern int verbosity;

/**
 * C source code writer related specialities
 */
extern std::ofstream c_file;
extern std::ofstream c_file_tables;
extern std::ofstream c_file_includes;
extern char          c_source_folder[];

/**
 * Debugging checks.
 */
extern unsigned debug;

/**
 * Whether to force windowed. Recommeded, as there is no guarantee that the
 * original display mode is available.
 */
extern bool forceWindowed;

/**
 * Add profiling data to the dump when retracing.
 */
extern bool profiling;
extern bool profilingCpuTimes;
extern bool profilingGpuTimes;
extern bool profilingPixelsDrawn;
extern bool profilingMemoryUsage;

/**
 * State dumping.
 */
extern bool dumpingState;
extern bool dumpingSnapshots;


enum Driver {
    DRIVER_DEFAULT,
    DRIVER_HARDWARE, // force hardware
    DRIVER_SOFTWARE,
    DRIVER_REFERENCE,
    DRIVER_NULL,
    DRIVER_MODULE,
};

extern Driver driver;
extern const char *driverModule;

extern bool doubleBuffer;
extern unsigned samples;

extern unsigned frameNo;
extern unsigned callNo;

extern trace::DumpFlags dumpFlags;

std::ostream &warning(trace::Call &call);

#ifdef _WIN32
void failed(trace::Call &call, HRESULT hr);
#endif

void checkMismatch(trace::Call &call, const char *expr, trace::Value *traceValue, long actualValue);

void ignore(trace::Call &call);
void unsupported(trace::Call &call);


typedef void (*Callback)(trace::Call &call);

struct Entry {
    const char *name;
    Callback callback;
};


struct stringComparer {
  bool operator() (const char *a, const  char *b) const {
    return strcmp(a, b) < 0;
  }
};


extern const Entry stdc_callbacks[];


class Retracer
{
    typedef std::map<const char *, Callback, stringComparer> Map;
    Map map;

    std::vector<Callback> callbacks;

public:
    Retracer() {
        addCallbacks(stdc_callbacks);
    }

    virtual ~Retracer() {}

    void addCallback(const Entry *entry);
    void addCallbacks(const Entry *entries);

    void retrace(trace::Call &call);
};


class Dumper
{
public:
    virtual image::Image *
    getSnapshot(void) = 0;

    virtual bool
    canDump(void) = 0;

    virtual void
    dumpState(StateWriter &) = 0;
};


extern Dumper *dumper;


void
setFeatureLevel(const char *featureLevel);

void
setUp(void);

void
addCallbacks(retrace::Retracer &retracer);

void
frameComplete(trace::Call &call);


/**
 * Flush rendering (called when switching threads).
 */
void
flushRendering(void);

/**
 * Finish rendering (called before exiting.)
 */
void
finishRendering(void);

void
waitForInput(void);

void
cleanUp(void);


} /* namespace retrace */

#define egl_stub_main_source "#include <stdio.h>\n" \
    "#include <stdlib.h>\n" \
    "#include \"includes.h\"\n" \
    "\n" \
    "Display               *dpy;\n" \
    "EGLDisplay            display;\n" \
    "EGLContext            context;\n" \
    "EGLSurface            surface;\n" \
    "\n" \
    "\n" \
    "static void run_trace()\n" \
    "{\n" \
    "\tcall_all_frames\n" \
    "\treturn;\n" \
    "}\n" \
    "\n" \
    "\n" \
    "static Bool WaitForNotify( Display *dpy, XEvent *event, XPointer arg ) {\n" \
    "\treturn (event->type == MapNotify) && (event->xmap.window == (Window) arg);\n" \
    "\t(void)dpy;\n" \
    "}\n" \
    "\n" \
    "int main( int argc, char *argv[] )\n" \
    "{\n" \
    "\tWindow               xWin;\n" \
    "\tXEvent               event;\n" \
    "\tXSetWindowAttributes swa;\n" \
    "\tEGLConfig            ecfg;\n" \
    "\tEGLint               num_config;\n" \
    "\n" \
    "\tload_all_blobs;\n" \
    "\n" \
    "\tdpy = XOpenDisplay(NULL);\n" \
    "\tif (dpy == NULL) {\n" \
    "\t\tprintf(\"Not able to connect to X server\\n\");\n" \
    "\t\texit(EXIT_FAILURE);\n" \
    "\t}\n" \
    "\n" \
    "\tswa.event_mask  =  StructureNotifyMask;\n" \
    "\n" \
    "\txWin = XCreateWindow(dpy, DefaultRootWindow(dpy), 0, 0, screensize0[0], screensize0[1],\n" \
    "\t\t0, CopyFromParent, InputOutput, CopyFromParent,\n" \
    "\t\tCWEventMask, &swa);\n" \
    "\n" \
    "\tXMapWindow(dpy, xWin);\n" \
    "\tXIfEvent(dpy, &event, WaitForNotify, (XPointer)xWin);\n" \
    "\n" \
    "\tdisplay  =  eglGetDisplay((EGLNativeDisplayType)dpy);\n" \
    "\tif (display == EGL_NO_DISPLAY) {\n" \
    "\t\tfprintf(stderr, \"Got no EGL display.\\n\");\n" \
    "\t\texit(EXIT_FAILURE);\n" \
    "\t}\n" \
    "\n" \
    "\tif (!eglInitialize(display, NULL, NULL)) {\n" \
    "\t\tfprintf(stderr, \"Unable to initialize EGL\\n\");\n" \
    "\t\texit(EXIT_FAILURE);\n" \
    "\t}\n" \
    "\n" \
    "\teglBindAPI(egl_api_bind0);\n" \
    "\n" \
    "\tif (!eglChooseConfig(display, egl_config_params0, &ecfg, 1,\n" \
    "\t\t&num_config)) {\n" \
    "\n" \
    "\t\tfprintf(stderr, \"Failed to choose config (eglError: 0x%x)\\n\",\n" \
    "\t\t\teglGetError());\n" \
    "\n" \
    "\t\texit(EXIT_FAILURE);\n" \
    "\t}\n" \
    "\n" \
    "\tif (num_config != 1) {\n" \
    "\t\tfprintf(stderr, \"Didn't get just one config, but %d\\n\", num_config);\n" \
    "\t\texit(EXIT_FAILURE);\n" \
    "\t}\n" \
    "\n" \
    "\tsurface = eglCreateWindowSurface(display, ecfg, xWin, NULL);\n" \
    "\tif (surface == EGL_NO_SURFACE) {\n" \
    "\t\tfprintf(stderr, \"Not able to create EGL surface (eglError: 0x%x)\\n\",\n" \
    "\t\t\teglGetError());\n" \
    "\t\texit(EXIT_FAILURE);\n" \
    "\t}\n" \
    "\n" \
    "\tcontext = eglCreateContext (display, ecfg, EGL_NO_CONTEXT,\n" \
    "\t\tegl_context_params0);\n" \
    "\n" \
    "\tif (context == EGL_NO_CONTEXT) {\n" \
    "\t\tfprintf(stderr, \"Not able to create EGL context (eglError: 0x%x)\\n\",\n" \
    "\t\t\teglGetError());\n" \
    "\n" \
    "\t\texit(EXIT_FAILURE);\n" \
    "\t}\n" \
    "\n" \
    "\teglMakeCurrent(display, surface, surface, context);\n" \
    "\n" \
    "\t/*\n" \
    "\t* Setup done. Now go to the trace.\n" \
    "\t*/\n" \
    "\trun_trace();\n" \
    "\n" \
    "\teglDestroyContext(display, context);\n" \
    "\teglDestroySurface(display, surface);\n" \
    "\teglTerminate(display);\n" \
    "\tXDestroyWindow(dpy, xWin);\n" \
    "\tXCloseDisplay(dpy);\n" \
    "\n" \
    "\tfree_all_blobs;\n" \
    "\n" \
    "\texit(EXIT_SUCCESS);\n" \
    "\n" \
    "\t(void)argc;\n" \
    "\t(void)argv;\n" \
    "}\n" \
    "\n"

#define egl_makefile "CC = gcc\n" \
    "\n" \
    "CFLAGS=$(shell pkg-config --cflags egl glesv2 x11)-Wall -ansi -O0 --std=c99\n" \
    "LIBS=$(shell pkg-config --libs egl glesv2 x11)\n" \
    "\n" \
    "SRCS=$(wildcard *.c)\n" \
    "OBJS=$(SRCS:.c=.o)\n" \
    "\n" \
    "%.o : %.c\n" \
    "\t$(CC) -c $(CFLAGS) $< -o $@\n" \
    "\n" \
    "egltest: $(OBJS)\n" \
    "\t$(CC) -o $@ $^ $(LIBS)\n" \
    "\n" \
    "clean:\n" \
    "\t@echo Cleaning up...\n" \
    "\t@rm egltest\n" \
    "\t@rm *.o\n" \
    "\t@echo Done.\n" \

#define glx_stub_main_source "#include <stdio.h>\n" \
    "#include <stdlib.h>\n" \
    "#include \"includes.h\"\n" \
    "\n" \
    "Display   *display;\n" \
    "GLXContext context;\n" \
    "Window     xWin;\n" \
    "\n" \
    "#ifdef use_glXCreateContextAttribsARB\n" \
    "typedef GLXContext (*GLXCREATECONTEXTATTRIBSARBPROC)(Display*, GLXFBConfig, GLXContext, Bool, const int*);\n" \
    "#endif\n" \
    "\n" \
    "static void run_trace()\n" \
    "{\n" \
    "\tcall_all_frames\n" \
    "\treturn;\n" \
    "}\n" \
    "\n" \
    "static Bool WaitForNotify( Display *dpy, XEvent *event, XPointer arg ) {\n" \
    "\treturn (event->type == MapNotify) && (event->xmap.window == (Window) arg);\n" \
    "\t(void)dpy;\n" \
    "}\n" \
    "\n" \
    "static int xerrorhandler(Display *dpy, XErrorEvent *error)\n" \
    "{\n" \
    "\tchar retError[256];\n" \
    "\tXGetErrorText(dpy, error->error_code, retError, sizeof(retError));\n" \
    "\tfprintf(stderr, \"Fatal error from X: %s\\n\", (char*)&retError);\n" \
    "\texit( EXIT_FAILURE);\n" \
    "}\n" \
    "\n" \
    "int main(int argc, char *argv[])\n" \
    "{\n" \
    "\tXEvent                event;\n" \
    "\tXVisualInfo          *vInfo;\n" \
    "\tXSetWindowAttributes  swa;\n" \
    "\tint                   swaMask;\n" \
    "#ifdef use_glXChooseFBConfig\n" \
    "\tint                   fbc_amount, c, chosen_fbc = -1, best_samples = -1, samp_buf, samples;\n" \
    "\tGLXFBConfig          *fbc;\n" \
   "#endif\n" \
   "#ifdef use_glXCreateContextAttribsARB\n" \
   "\tGLXCREATECONTEXTATTRIBSARBPROC glXCreateContextAttribsARB;\n" \
   "#endif\n" \
    "\n" \
    "\tload_all_blobs;\n" \
    "\n" \
    "\tdisplay = XOpenDisplay(NULL);\n" \
    "\tif (display == NULL) {\n" \
    "\t\tprintf( \"Unable to open a connection to the X server\\n\" );\n" \
    "\t\texit( EXIT_FAILURE );\n" \
    "\t}\n" \
    "\n" \
    "\tXSetErrorHandler(xerrorhandler);\n" \
    "\n" \
    "#ifdef use_glXChooseFBConfig\n" \
    "\tfbc = glXChooseFBConfig(display, DefaultScreen(display),\n" \
    "\t\t\t\t\t\t\tglx_visual_params0, &fbc_amount);\n" \
    "\n" \
    "\tif (fbc == 0) {\n" \
    "\t\tprintf( \"Not able to find matching framebuffer\\n\" );\n" \
    "\t\texit( EXIT_FAILURE );\n" \
    "\t}\n" \
    "\tfor (c = 0; c < fbc_amount; c++) {\n" \
    "\t\tvInfo = glXGetVisualFromFBConfig(display, fbc[c]);\n" \
    "\t\tif (vInfo) {\n" \
    "\t\t\tglXGetFBConfigAttrib(display, fbc[c], GLX_SAMPLE_BUFFERS, &samp_buf);\n" \
    "\t\t\tglXGetFBConfigAttrib(display, fbc[c], GLX_SAMPLES, &samples);\n" \
    "\n" \
    "#ifdef DEBUG\n" \
    "\t\t\tprintf(\"GLXFBConfig %d, id 0x%2x sample buffers %d, samples = %d\\n\", c, (unsigned int)vInfo->visualid, samp_buf, samples );\n" \
    "#endif\n" \
    "\n" \
    "\t\tif (chosen_fbc < 0 || (samp_buf && samples > best_samples))\n" \
    "\t\t\tchosen_fbc = c, best_samples = samples;\n" \
    "\t\t}\n" \
    "\t\tXFree(vInfo);\n" \
    "\t}\n" \
    "\tvInfo = glXGetVisualFromFBConfig(display, fbc[chosen_fbc]);\n" \
    "#ifdef DEBUG\n" \
    "\tprintf(\"chosen visual = 0x%x\\n\", (unsigned int)vInfo->visualid);\n" \
    "#endif\n" \
    "#else\n" \
    "\tvInfo = glXChooseVisual(display, 0, glx_visual_params0);\n" \
    "#endif\n" \
    "\n" \
    "\tswa.colormap = XCreateColormap( display, RootWindow(display, vInfo->screen),\n" \
    "\t\t\t\t\t\t\tvInfo->visual, AllocNone );\n" \
    "\tswa.event_mask = StructureNotifyMask;\n" \
    "\tswaMask = CWColormap | CWEventMask;\n" \
    "\n" \
    "\txWin = XCreateWindow(display, RootWindow(display, vInfo->screen), 0, 0, screensize0[0], screensize0[1],\n" \
    "\t\t0, vInfo->depth, InputOutput, vInfo->visual,\n" \
    "\t\tswaMask, &swa);\n" \
    "\n" \
    "#ifdef use_glXCreateContextAttribsARB\n" \
    "\tglXCreateContextAttribsARB = (GLXCREATECONTEXTATTRIBSARBPROC) \n" \
    "\t\tglXGetProcAddress((const GLubyte*)\"glXCreateContextAttribsARB\");\n" \
    "\n" \
    "\tcontext = glXCreateContextAttribsARB(display, fbc[chosen_fbc], NULL, True,\n" \
    "\t\t\tContextAttribsARB0);\n" \
    "#else\n" \
    "\tcontext = glXCreateContext( display, vInfo, NULL, True );\n" \
    "#endif\n" \
    "#ifdef use_glXChooseFBConfig\n" \
    "\tXFree(fbc);\n" \
    "#endif\n" \
    "\n" \
    "\tXMapWindow(display, xWin);\n" \
    "\tXIfEvent(display, &event, WaitForNotify, (XPointer) xWin);\n" \
    "\n" \
    "\tglXMakeCurrent(display, xWin, context);\n" \
    "\n" \
    "\t/*\n" \
    "\t* Setup done. Now go to the trace.\n" \
    "\t*/\n" \
    "\trun_trace();\n" \
    "\n" \
    "\tglXMakeContextCurrent(display, 0, 0, 0);\n" \
    "\tglXDestroyContext(display, context);\n" \
    "\tXDestroyWindow(display, xWin);\n" \
    "\tXFree(vInfo);\n" \
    "\tXCloseDisplay(display);\n" \
    "\n" \
    "\tfree_all_blobs;\n" \
    "\n" \
    "\texit( EXIT_SUCCESS );\n" \
    "\n" \
    "\t(void)argc;\n" \
    "\t(void)argv;\n" \
    "}\n"

#define glx_makefile "CC = gcc\n" \
    "\n" \
    "CFLAGS=$(shell pkg-config --cflags gl x11 glu)-ansi -O0 --std=c99\n" \
    "LIBS=$(shell pkg-config --libs gl x11 glu)\n" \
    "\n" \
    "all: CFLAGS += -w\n" \
    "all: glxtest\n" \
    "\n" \
    "debug: CFLAGS += -Wall -g -DDEBUG\n" \
    "debug: glxtest\n" \
    "\n" \
    "SRCS=$(wildcard *.c)\n" \
    "OBJS=$(SRCS:.c=.o)\n" \
    "\n" \
    "%.o : %.c\n" \
    "\t$(CC) -c $(CFLAGS) $< -o $@\n" \
    "\n" \
    "glxtest: $(OBJS)\n" \
    "\t$(CC) -o $@ $^ $(LIBS)\n" \
    "\n" \
    "clean:\n" \
    "\t	rm -f glxtest $(OBJS)\n"

