/**************************************************************************
 *
 * Copyright 2007-2011 VMware, Inc.
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


#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "os.hpp"
#include "os_thread.hpp"
#include "os_string.hpp"
#include "os_version.hpp"
#include "trace_file.hpp"
#include "trace_writer_local.hpp"
#include "trace_format.hpp"
#include "os_backtrace.hpp"

extern "C" {

extern void stateRebuild(void);
};

namespace trace {


static const char *memcpy_args[3] = {"dest", "src", "n"};
const FunctionSig memcpy_sig = {0, "memcpy", 3, memcpy_args};

static const char *malloc_args[1] = {"size"};
const FunctionSig malloc_sig = {1, "malloc", 1, malloc_args};

static const char *free_args[1] = {"ptr"};
const FunctionSig free_sig = {2, "free", 1, free_args};

static const char *realloc_args[2] = {"ptr", "size"};
const FunctionSig realloc_sig = {3, "realloc", 2, realloc_args};

#ifdef __linux__
static const char *capture_starter_filename = \
        "/tmp/apitrace_capture_frame_now.txt";
#endif

#ifdef ANDROID
static const char *capture_starter_filename = \
        "/data/data/apitrace_capture_frame_now.txt";
#endif

static void exceptionCallback(void)
{
    localWriter.flush();
}


bool LocalWriter::checkSingleFrameCaptureRequest(void) {
    struct  stat file_stat;
    char    fileread[256];
    int     err, rVal;

    err = stat(capture_starter_filename, &file_stat);
    if (err != 0) {
        return false;
    }

    if (difftime(file_stat.st_mtim.tv_sec, oldFileModTime.tv_sec) < 1)
        return false;

    oldFileModTime = file_stat.st_mtim;

    FILE *fp = fopen(capture_starter_filename, "ra");
    if (!fp)
        return false;

    memset((void*)&fileread, sizeof(fileread), 1);
    fread((void*)&fileread, 1, std::min((int)file_stat.st_size, \
                                        (int)sizeof(fileread)), fp);
    fclose(fp);

    rVal = atoi(fileread);
    if (rVal > 0) {
        framesRemainingToCapture = rVal+1;
        return true;
    }
    return false;
}

LocalWriter::LocalWriter() :
    acquired(0)
{
    os::String process = os::getProcessName();
    os::log("apitrace: loaded into %s\n", process.str());

    // Install the signal handlers as early as possible, to prevent
    // interfering with the application's signal handling.
    os::setExceptionCallback(exceptionCallback);

#if defined (__linux__) || defined (ANDROID)
    if (getenv("APITRACE_SINGLE_FRAME_CAPTURE_MODE") != NULL) {
        singleFrameCaptureMode = true;
        isSwapBufferCall = false;
        displayListNumber = 0;
        char zerostring[] = "0";
        FILE *fp = fopen(capture_starter_filename, "wa");
        fwrite((void*)zerostring, 1, sizeof(*zerostring), fp);
        fclose(fp);

        struct  stat file_stat;
        stat(capture_starter_filename, &file_stat);
        oldFileModTime = file_stat.st_mtim;
    }
#endif
}

LocalWriter::~LocalWriter()
{
    os::resetExceptionCallback();
    checkProcessId();
#if defined (__linux__) || defined (ANDROID)
    if (singleFrameCaptureMode)
        remove(capture_starter_filename);
#endif
}

void
LocalWriter::open(void) {
    os::String szFileName;

    const char *lpFileName;

    lpFileName = getenv("TRACE_FILE");
    if (!lpFileName) {
        static unsigned dwCounter = 0;

        os::String process = os::getProcessName();
#ifdef _WIN32
        process.trimExtension();
#endif
        process.trimDirectory();

#ifdef ANDROID
        os::String prefix = "/data/data";
        prefix.join(process);
#else
        os::String prefix = os::getCurrentDir();
#ifdef _WIN32
        // Avoid writing into Windows' system directory as quite often access
        // will be denied.
        if (IsWindows8OrGreater()) {
            char szDirectory[MAX_PATH + 1];
            GetSystemDirectoryA(szDirectory, sizeof szDirectory);
            if (stricmp(prefix, szDirectory) == 0) {
                GetTempPathA(sizeof szDirectory, szDirectory);
                prefix = szDirectory;
            }
        }
#endif
#endif
        prefix.join(process);

        for (;;) {
            FILE *file;

            if (dwCounter)
                szFileName = os::String::format("%s.%u.trace", prefix.str(), dwCounter);
            else
                szFileName = os::String::format("%s.trace", prefix.str());

            lpFileName = szFileName;
            file = fopen(lpFileName, "rb");
            if (file == NULL)
                break;

            fclose(file);

            ++dwCounter;
        }
    }

    os::log("apitrace: tracing to %s\n", lpFileName);

    if (!Writer::open(lpFileName)) {
        os::log("apitrace: error: failed to open %s\n", lpFileName);
        os::abort();
    }

    pid = os::getCurrentProcessId();

#if 0
    // For debugging the exception handler
    *((int *)0) = 0;
#endif
}

static uintptr_t next_thread_num = 1;

static OS_THREAD_SPECIFIC(uintptr_t)
thread_num;

void LocalWriter::checkProcessId(void) {
    if (m_file->isOpened() &&
        os::getCurrentProcessId() != pid) {
        // We are a forked child process that inherited the trace file, so
        // create a new file.  We can't call any method of the current
        // file, as it may cause it to flush and corrupt the parent's
        // trace, so we effectively leak the old file object.
        m_file = File::createSnappy();
        // Don't want to open the same file again
        os::unsetEnvironment("TRACE_FILE");
        open();
    }
}

unsigned LocalWriter::beginEnter(const FunctionSig *sig, bool fake) {
    mutex.lock();
    ++acquired;

    signame = sig->name;

    forceWriteFlag = false;
    isSwapBufferCall = strcmp(signame, "glXSwapBuffers")==0?true:false;

    if (strcmp(signame, "glGenLists")==0)
        displayListNumber++;

    if (displayListNumber > 0)
        forceWriteFlag = true;

    if (strncmp(signame, "glX", 3) == 0 &&
            !(isSwapBufferCall&&framesRemainingToCapture < 0)) {
        if (strcmp(signame, "glXWaitGL") == 0 ||
                strcmp(signame, "glXWaitX") == 0)
            forceWriteFlag = false;
        else
            forceWriteFlag = true;
    }

    if (isSwapBufferCall&&framesRemainingToCapture >= 0)
        forceWriteFlag = true;


    checkProcessId();

    if (singleFrameCaptureMode && !forceWriteFlag &&
            framesRemainingToCapture <= 0) {
        return 0;
    }

    if (!m_file->isOpened()) {
        open();
    }

    uintptr_t this_thread_num = thread_num;
    if (!this_thread_num) {
        this_thread_num = next_thread_num++;
        thread_num = this_thread_num;
    }

    assert(this_thread_num);
    unsigned thread_id = this_thread_num - 1;
    unsigned call_no = Writer::beginEnter(sig, thread_id);
    if (!fake && os::backtrace_is_needed(sig->name)) {
        std::vector<RawStackFrame> backtrace = os::get_backtrace();
        beginBacktrace(backtrace.size());
        for (unsigned i = 0; i < backtrace.size(); ++i) {
            writeStackFrame(&backtrace[i]);
        }
        endBacktrace();
    }
    return call_no;
}

void LocalWriter::endEnter(void) {
    if (WRITE_TRACE) {
        Writer::endEnter();
    }

    --acquired;
    mutex.unlock();
}

void LocalWriter::beginLeave(unsigned call) {
    mutex.lock();
    ++acquired;

    if (WRITE_TRACE) {
        Writer::beginLeave(call);
    }
}

void LocalWriter::endLeave(void) {
    if (WRITE_TRACE) {
        Writer::endLeave();
    }

    --acquired;
    mutex.unlock();

    if (singleFrameCaptureMode && isSwapBufferCall)
    {
        if (!forceWriteFlag || framesRemainingToCapture < 0) {
            /*
             * accept new capture requests only after old one
             * has been handled. this is to avoid silly problems
             * with state rebuilding.
             */
            if (checkSingleFrameCaptureRequest()) {
                ::stateRebuild();
            }
        }

        if (framesRemainingToCapture >= 0) {
            framesRemainingToCapture--;
        }

        if (framesRemainingToCapture == 0) {
            framesRemainingToCapture = -1;
        }
    }

    if (forceWriteFlag && strcmp(signame, "glEndList")==0) {
        displayListNumber--;
    }
}

void LocalWriter::flush(void) {
    /*
     * Do nothing if the mutex is already acquired (e.g., if a segfault happen
     * while writing the file) as state could be inconsistent, therefore yield
     * inconsistent trace files and/or repeated segfaults till infinity.
     */

    mutex.lock();
    if (acquired) {
        os::log("apitrace: ignoring exception while tracing\n");
    } else {
        ++acquired;
        if (m_file->isOpened()) {
            if (os::getCurrentProcessId() != pid) {
                os::log("apitrace: ignoring exception in child process\n");
            } else {
                os::log("apitrace: flushing trace due to an exception\n");
                m_file->flush();
            }
        }
        --acquired;
    }
    mutex.unlock();
}


LocalWriter localWriter;


void fakeMemcpy(const void *ptr, size_t size) {
    assert(ptr);
    if (!size) {
        return;
    }
    unsigned _call = localWriter.beginEnter(&memcpy_sig, true);
    localWriter.beginArg(0);
    localWriter.writePointer((uintptr_t)ptr);
    localWriter.endArg();
    localWriter.beginArg(1);
    localWriter.writeBlob(ptr, size);
    localWriter.endArg();
    localWriter.beginArg(2);
    localWriter.writeUInt(size);
    localWriter.endArg();
    localWriter.endEnter();
    localWriter.beginLeave(_call);
    localWriter.endLeave();
}



} /* namespace trace */
