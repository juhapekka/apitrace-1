/**************************************************************************
 *
 * Copyright 2010 VMware, Inc.
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


#include <limits>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <GL/gl.h>

#include <assert.h>
#include <string.h>
#include <math.h>

#include "highlight.hpp"
#include "trace_dump.hpp"
#include "guids.hpp"


namespace trace {

char* blobnamebuffer = NULL;
char  blobname[512];
int blobnamebuffersize = 0;
const char* currentargname = NULL;
bool write_to_inlcude = false;
int stringcounter = 0;
unsigned int last_uint_val = 0;
const char *sep = "";
const char* sig = NULL;


int* buffers_enabled = NULL;
int* arrays_enabled = NULL;
int* textures_enabled = NULL;
int* framebuffers_enabled = NULL;
int* renderbuffers_enabled = NULL;
int* ids_enabled = NULL;
int* samplers_enabled = NULL;
int* programs_enabled = NULL;

char write_folder[1024];

class Dumper : public Visitor
{
protected:
    std::ostream &os;
    std::ostream &os_c_course_tables;
    std::ostream &os_c_include;
    DumpFlags dumpFlags;
    const highlight::Highlighter & highlighter;
    const highlight::Attribute & normal;
    const highlight::Attribute & bold;
    const highlight::Attribute & italic;
    const highlight::Attribute & strike;
    const highlight::Attribute & red;
    const highlight::Attribute & pointer;
    const highlight::Attribute & literal;

public:
/*
    Dumper(std::ostream &_os, DumpFlags _flags) :
        os(_os),
        os_c_course_include(NULL),
        dumpFlags(_flags),
        highlighter(highlight::defaultHighlighter(!(dumpFlags & DUMP_FLAG_NO_COLOR))),
        normal(highlighter.normal()),
        bold(highlighter.bold()),
        italic(highlighter.italic()),
        strike(highlighter.strike()),
        red(highlighter.color(highlight::RED)),
        pointer(highlighter.color(highlight::GREEN)),
        literal(highlighter.color(highlight::BLUE))
    {
    }
*/
    Dumper(std::ostream &_os, std::ostream &_os2, std::ostream &_os3, DumpFlags _flags) :
        os(_os),
        os_c_course_tables(_os2),
        os_c_include(_os3),
        dumpFlags(_flags),
        highlighter(highlight::defaultHighlighter(!(dumpFlags & DUMP_FLAG_NO_COLOR))),
        normal(highlighter.normal()),
        bold(highlighter.bold()),
        italic(highlighter.italic()),
        strike(highlighter.strike()),
        red(highlighter.color(highlight::RED)),
        pointer(highlighter.color(highlight::GREEN)),
        literal(highlighter.color(highlight::BLUE))
    {
        sep = ", ";
    }


    ~Dumper() {
    }

    void visit(Null *) {
        if (strlen(sep)<1)
        {
            os << ((dumpFlags&trace::DUMP_FLAG_C_SOURCE)?"(int[]) {":"{");
        }
        if (dumpFlags&trace::DUMP_FLAG_C_SOURCE)
            os << "NULL";
        else
            os << literal << "NULL" << normal;
    }

    void visit(Bool *node) {
        if (strlen(sep)<1)
        {
            os << ((dumpFlags&trace::DUMP_FLAG_C_SOURCE)?"(bool[]) {":"{");
        }
        if (dumpFlags&trace::DUMP_FLAG_C_SOURCE)
            os << literal << (node->value ? "true" : "false");
        else
            os << (node->value ? "true" : "false");
    }

    void visit(SInt *node) {
        if (strlen(sep)<1)
        {
            os << ((dumpFlags&trace::DUMP_FLAG_C_SOURCE)?"(int[]) {":"{");
        }
        if (dumpFlags&trace::DUMP_FLAG_C_SOURCE)
            if (write_to_inlcude) {
                ;
//                os_c_course_tables << std::dec << node->value << ";\n";
//                os_c_include << std::dec << node->value << ";\n";
            }
            else {
                if(strcmp(currentargname, "drawable")==0) {
                    os << "xWin";
                    return;
                }
                os << std::dec << node->value;
            }
        else
            os << literal << node->value << normal;
    }

    void visit(UInt *node) {
        if (strlen(sep)<1)
        {
            os << ((dumpFlags&trace::DUMP_FLAG_C_SOURCE)?"(unsigned int[]) {":"{");
        }
        if (dumpFlags&trace::DUMP_FLAG_C_SOURCE) {
           const struct
           {
              char   name[16];
              int    namelenght;
              int** list;
           } handled_resources_pointer[] =
           {
              {"buffer", 6, &buffers_enabled },
              {"texture", 7, &textures_enabled },
              {"array", 5, &arrays_enabled },
              {"framebuffer", 11, &framebuffers_enabled },
              {"renderbuffer", 13, &renderbuffers_enabled },
              {"id", 2, &ids_enabled },
              {"sampler", 7, &samplers_enabled },
              {"program", 7, &programs_enabled },
           };

           const struct
           {
              char   name[16];
              char   outputname[16];
           } handled_resources[] =
           {
              {"program", "_programs" },
              {"shader", "shader" },
           };


           if (strncmp("glGen", sig, 5)== 0 || 
               strncmp("glDelete", sig, 8)== 0) {
              last_uint_val = node->value;

              for (int c = 0; c < sizeof(handled_resources_pointer)/sizeof(handled_resources_pointer[0]); c++) {

                 if(strncmp(currentargname, handled_resources_pointer[c].name, handled_resources_pointer[c].namelenght) == 0) {

                    for (int i = 0; i < (*handled_resources_pointer[c].list)[0]; i++) {
                       if ((*handled_resources_pointer[c].list)[i+1] == last_uint_val )
                          goto already_stored_this;
                    }

                    os_c_course_tables << "unsigned int _" << handled_resources_pointer[c].name 
                                        << "s" << "_" << std::dec << last_uint_val
                                        << " = "  << last_uint_val << ";\n";

                    os_c_course_tables << "unsigned int* _" << handled_resources_pointer[c].name 
                                        << "s" << "_" << std::dec << last_uint_val 
                                        << "_p = &_" << handled_resources_pointer[c].name  
                                        << "s" << "_"
                                        << std::dec << last_uint_val << ";\n";

                    os_c_include << "extern unsigned int _" << handled_resources_pointer[c].name 
                                  << "s" << "_" << std::dec << last_uint_val<< ";\n";

                    os_c_include << "extern unsigned int* _" << handled_resources_pointer[c].name
                                  << "s" << "_" << std::dec << last_uint_val << "_p;\n";

                    (*handled_resources_pointer[c].list)[0]++;
                    (*handled_resources_pointer[c].list)[(*handled_resources_pointer[c].list)[0]] = last_uint_val;
already_stored_this:;
                 }
              }
           }
           else
              last_uint_val = node->value;

            if (write_to_inlcude) {
//                os_c_course_tables << std::dec << node->value << ";\n";
//                os_c_include << std::dec << node->value << ";\n";
            }
            else {
               for (int c = 0; c < 2; c++) {
                  
                  if(strcmp(currentargname, handled_resources[c].name) == 0) {
                     os << handled_resources[c].outputname << "_"  << std::dec
                        << node->value;
                     return;
                  }
               }

               for (int c = 0; c < sizeof(handled_resources_pointer)/sizeof(handled_resources_pointer[0]); c++) {
                  if(strncmp(currentargname, handled_resources_pointer[c].name, handled_resources_pointer[c].namelenght) == 0) {
                     os << "*_" << handled_resources_pointer[c].name << "s" << "_"  
                        << std::dec << node->value << "_p";

                     if (strncmp("glBind", sig, 6)== 0) {

                        int *list = *handled_resources_pointer[c].list;
                        int comp = list[0]/*+1*/;
                        for (int i = 0; i < comp; i++) {
                           int cc = (*handled_resources_pointer[c].list)[i+1];
                           if (cc == last_uint_val ) {
                              goto already_stored_this2;
                           }
                        }

                        os_c_course_tables << "unsigned int _" << handled_resources_pointer[c].name 
                                            << "s" << "_" << std::dec << last_uint_val
                                            << " = "  << last_uint_val << ";\n";

                        os_c_course_tables << "unsigned int* _" << handled_resources_pointer[c].name 
                                            << "s" << "_" << std::dec << last_uint_val
                                            << "_p = &_" << handled_resources_pointer[c].name  
                                            << "s" << "_"
                                            << std::dec << last_uint_val << ";\n";

                        os_c_include << "extern unsigned int _" << handled_resources_pointer[c].name 
                                      << "s" << "_" << std::dec << last_uint_val << ";\n";

                        os_c_include << "extern unsigned int* _" << handled_resources_pointer[c].name
                                      << "s" << "_" << std::dec << last_uint_val << "_p;\n";
                     }

                     (*handled_resources_pointer[c].list)[(*handled_resources_pointer[c].list)[0]+1] = last_uint_val;
                     (*handled_resources_pointer[c].list)[0]++;
already_stored_this2:
                     return;
                  }
               }

               if(strcmp(currentargname, "drawable")==0) {
                    os << "xWin";
                    return;
                }
                os << std::dec << node->value;
            }
        }
        else
            os << literal << node->value << normal;
    }

    void visit(Float *node) {
        if (strlen(sep)<1)
        {
            os << ((dumpFlags&trace::DUMP_FLAG_C_SOURCE)?"(float[]) {":"{");
        }
        std::streamsize oldPrecision = os.precision(std::numeric_limits<float>::digits10 + 1);
        if (dumpFlags&trace::DUMP_FLAG_C_SOURCE)
            if (isfinite(node->value)) {
               os << node->value;
            }
        else
            {
               if(node->value == -INFINITY)
                  os << "-INFINITY";
               else
                  os << "INFINITY";
            }
        else
            os << literal << node->value << normal;
        os.precision(oldPrecision);
    }

    void visit(Double *node) {
        if (strlen(sep)<1)
        {
            os << ((dumpFlags&trace::DUMP_FLAG_C_SOURCE)?"(double[]) {":"{");
        }
        std::streamsize oldPrecision = os.precision(std::numeric_limits<double>::digits10 + 1);
        if (dumpFlags&trace::DUMP_FLAG_C_SOURCE)
            os << node->value;
        else
            os << literal << node->value << normal;
        os.precision(oldPrecision);
    }

    template< typename C >
    void visitString(const C *value) {
        std::ostream &redirect((dumpFlags&trace::DUMP_FLAG_C_SOURCE&&
                                (strcmp(currentargname, "string")==0 ||
                                 strcmp(currentargname, "varyings") == 0))?
                                  os_c_course_tables:os);

        if (dumpFlags&trace::DUMP_FLAG_C_SOURCE) {
            redirect <<"\"";
        }
        else {
            redirect << literal << "\"";
        }

        for (const C *it = value; *it; ++it) {
            unsigned c = (unsigned) *it;
            if (c == '\"')
                redirect << "\\\"";
            else if (c == '\\')
                redirect << "\\\\";
            else if (c >= 0x20 && c <= 0x7e)
                redirect << (char)c;
            else if (c == '\t') {
                redirect << "\t";
            } else if (c == '\r') {
                // Ignore carriage-return
            } else if (c == '\n') {
                // Reset formatting so that it looks correct with 'less -R'
                if (dumpFlags&trace::DUMP_FLAG_C_SOURCE) {
                    if (it[1] == 0)
                        redirect << "\\n \\\n";
                    else
                        redirect << "\\n\\\n";
                }
                else
                    redirect << normal << '\n' << literal;
            } else {
                // FIXME: handle wchar_t octals properly
                unsigned octal0 = c & 0x7;
                unsigned octal1 = (c >> 3) & 0x7;
                unsigned octal2 = (c >> 3) & 0x7;
                redirect << "\\";
                if (octal2)
                    redirect << octal2;
                if (octal1)
                    redirect << octal1;
                redirect << octal0;
            }
        }
        if (dumpFlags&DUMP_FLAG_C_SOURCE) {
//            if (strcmp(currentargname, "string")!=0) {
               redirect << "\"";
//            }
        }
        else {
            redirect << "\"" << normal;
        }
    }

    void visit(String *node) {
        if (dumpFlags&DUMP_FLAG_C_SOURCE && sig &&
            (strncmp(sig, "glShaderSource", 14) == 0||
             strncmp(sig, "glTransformFeedbackVaryings", 27) == 0 ||
             strncmp(sig, "glProgramStringARB", 18) == 0)) {
            static int storenum = 0, increased = 0;

            if (storenum != trace::stringcounter) {
               storenum = trace::stringcounter;
               increased = 0;
            }

            std::ofstream tempstream;
            char newname[1024];
            sprintf((char*)&newname, "%s/_%s_%d_%d", write_folder, currentargname,
                    trace::stringcounter, increased);

            tempstream.open(newname);
            tempstream.write(node->toString(), strlen(node->toString()));
            tempstream.close();
///////////
            sprintf((char*)&newname, "_%s_%d_%d", currentargname,
                    trace::stringcounter, increased);

            char* bb = blobnamebuffer;

            for (unsigned i = 0 ; i < blobnamebuffersize;
                 i++, bb += strlen(bb)+1) {
            }

            blobnamebuffer = (char*)realloc( blobnamebuffer,(bb-blobnamebuffer)+
                                     strlen((char*)&newname)+1);

            bb = blobnamebuffer;
            for (unsigned i = 0 ; i < blobnamebuffersize;
                 i++, bb += strlen(bb)+1) {
            }
            memcpy(bb, (void*)&newname, strlen((char*)&newname)+1);
            blobnamebuffersize++;
///////////////////
            
            if (strncmp(sig, "glProgramStringARB", 18) == 0) {
               sprintf((char*)&newname, "_%s_%d_p[%d]", currentargname,
                       trace::stringcounter, increased);
               os << newname;
            }

            increased++;
            return;
        }
        visitString(node->value);
    }

    void visit(WString *node) {
        if (dumpFlags&DUMP_FLAG_C_SOURCE)
            os << "L";
        else
            os << literal << "L";
        visitString(node->value);
    }

    void visit(Enum *node) {
        if (strlen(sep)<1)
        {
            os << ((dumpFlags&trace::DUMP_FLAG_C_SOURCE)?"(const GLenum[]) {":"{");
        }
        const EnumValue *it = node->lookup();
        if (it) {
            if (dumpFlags&DUMP_FLAG_C_SOURCE) {
/*                if (write_to_inlcude) {
                   ;
//                    os_c_course_tables << " = " << it->name;
                }
                else {*/
                    os << it->name;
/*                }*/
            }
            else {
                os << literal << it->name << normal;
            }
            return;
        }
        if (dumpFlags&DUMP_FLAG_C_SOURCE) {
            if (write_to_inlcude) {
                os_c_course_tables << " = " << node->value;
            }
            else {
                os << node->value;
            }
        }
        else {
            os << literal << node->value << normal;
        }
    }

    void visit(Bitmask *bitmask) {
        unsigned long long value = bitmask->value;
        const BitmaskSig *sig = bitmask->sig;
        bool first = true;
        for (const BitmaskFlag *it = sig->flags; it != sig->flags + sig->num_flags; ++it) {
            assert(it->value || first);
            if ((it->value && (value & it->value) == it->value) ||
                (!it->value && value == 0)) {
                if (!first) {
                    os << " | ";
                }
                if (dumpFlags&DUMP_FLAG_C_SOURCE)
                    os << it->name;
                else
                    os << literal << it->name << normal;
                value &= ~it->value;
                first = false;
            }
            if (value == 0) {
                break;
            }
        }
        if (value || first) {
            if (!first) {
                os << " | ";
            }
            if (dumpFlags&DUMP_FLAG_C_SOURCE)
                os << "0x" << std::hex << value << std::dec;
            else
                os << literal << "0x" << std::hex << value << std::dec << normal;
        }
    }

    const char *
    visitMembers(Struct *s, const char *sep = "") {
        for (unsigned i = 0; i < s->members.size(); ++i) {
            const char *memberName = s->sig->member_names[i];
            Value *memberValue = s->members[i];

            if (!memberName || !*memberName) {
                // Anonymous structure
                Struct *memberStruct = memberValue->toStruct();
                assert(memberStruct);
                if (memberStruct) {
                    sep = visitMembers(memberStruct, sep);
                    continue;
                }
            }

            if (!dumpFlags&trace::DUMP_FLAG_NO_ARG_NAMES) {
                os << sep << memberName << " = ";
            }
            else
                os << sep << italic << memberName << normal << " = ";
            _visit(memberValue);
            sep = ", ";
        }
        return sep;
    }

    void visit(Struct *s) {
        // Replace GUIDs with their symbolic name
        // TODO: Move this to parsing, so it can be shared everywhere
        if (s->members.size() == 4 &&
            strcmp(s->sig->name, "GUID") == 0) {
            GUID guid;
            guid.Data1 = s->members[0]->toUInt();
            guid.Data2 = s->members[1]->toUInt();
            guid.Data3 = s->members[2]->toUInt();
            Array *data4 = s->members[3]->toArray();
            assert(data4);
            assert(data4->values.size() == 8);
            for (int i = 0; i < sizeof guid.Data4; ++i) {
                guid.Data4[i] = data4->values[i]->toUInt();
            }
            const char *name = getGuidName(guid);
            os << literal << name << normal;
            return;
        }

        os << "{";
        visitMembers(s);
        os << "}";
    }

    void visit(Array *array) {
        unsigned char names[256];

        if (array->values.size() == 1) {
            if (dumpFlags&DUMP_FLAG_C_SOURCE) {
                sprintf( (char*)&names, "_%s_", currentargname);
                if ((strcmp(currentargname, "string")==0 ||
                     strcmp(currentargname, "varyings") == 0)) {
                    os << names << std::dec << stringcounter << "_p";

                    os_c_include << "extern char** "
                                        << names << std::dec << stringcounter
                                        << "_p;\n";

                    write_to_inlcude = true;
                    _visit(array->values[0]);
                    write_to_inlcude = false;

                }
                else {
                   if (strncmp(sig, "glShaderSource", 14)==0 ) 
                   {
                      /*
                       * if need to cludge for now.. :/
                       */
                      os << "NULL";
                   }
                   else
                   {
/*                      if (array->values[0])
*/
                       write_to_inlcude = true;
                       _visit(array->values[0]);
                       write_to_inlcude = false;
   
                       os << "_" <<currentargname << ((strcmp(currentargname, "buffer")==0)?"s_":"_") <<
                             std::dec << last_uint_val << "_p";

/*                    if (strncmp("glGen", sig, 5)== 0 ) {
                       os_c_course_tables << "unsigned int " << names << std::dec << last_uint_val+1 << " = " << last_uint_val+1 << ";\n";
                       
                       os_c_course_tables << "unsigned int* " << names << std::dec << last_uint_val+1 << "_p = &" << names << std::dec << last_uint_val+1 << ";\n";
                       os_c_include << "extern unsigned int " << names << std::dec << last_uint_val+ 1<< ";\n";
                       os_c_include << "extern unsigned int* " << names << std::dec << last_uint_val+1 << "_p;\n";
                    }*/
                   }

                }

                if ((strcmp(currentargname, "string")==0 ||
                     strcmp(currentargname, "varyings") == 0)) {
                    os_c_course_tables << "char** " << names << \
                                           std::dec << stringcounter << \
                                           "_p;\n";
                }
                stringcounter++;
                currentargname = (const char*)NULL;
            }
            else {
                os << "&";
                _visit(array->values[0]);
            }
        }
        else {
            if (dumpFlags&DUMP_FLAG_C_SOURCE) {
                sprintf( (char*)&names, "_%s_", currentargname);
                if (strcmp(currentargname, "string")==0 || 
                    strcmp(currentargname, "varyings")==0) {
                    os << /*"&" << */names << std::dec << stringcounter << "_p";

/*                    os_c_course_tables << "unsigned char "
                                        << names << std::dec << stringcounter
                                        << "[][131072] = {";*/
                    os_c_course_tables << "char** "
                                       << names << std::dec << stringcounter
                                       << "_p;\n";


                    os_c_include << "extern char** "
                                        << names << std::dec << stringcounter
                                        << "_p;\n";
/*                    os_c_include << "extern unsigned char "
                                        << names << std::dec << stringcounter
                                        << "[][131072];\n";*/

                    write_to_inlcude = true;
                    sep = "";
                    for (std::vector<Value *>::iterator it = array->values.begin(); it != array->values.end(); ++it) {
/*                        os_c_course_tables << sep;
                        os_c_course_tables << "{"; */
                        _visit(*it);
/*                        os_c_course_tables << "}";*/
                        sep = ", ";
                    }
/*                    if (strlen(sep)<1) {
                        os_c_course_tables << "NULL";
                    }
                    else {
                        os_c_course_tables << "};\n\n";
                    }*/
                    write_to_inlcude = false;
                }
                else {
                    sep = "";
                    for (std::vector<Value *>::iterator it = array->values.begin(); it != array->values.end(); ++it) {
                        os << sep;
                        _visit(*it);
                        sep = ", ";
                    }
                    if (strlen(sep)<1) {
                        os << "NULL";
                    }
                    else {
                        os << "}";
                    }
                }

/*                if (strcmp(currentargname, "string")==0) {
                    os_c_course_tables << "unsigned char* " << names << \
                                           std::dec << stringcounter << \
                                           "_p[] = {";
                    for ( int i = 0; i < array->values.size(); i++) {
                        os_c_course_tables << "&" << names << std::dec
                                           << stringcounter << "[" << i
                                           << "], ";
                        if ((i&7) == 0)
                            os_c_course_tables << "\\\n    ";
                    }
                    os_c_course_tables << "};\n\n";

                }*/
                stringcounter++;
                currentargname = (const char*)NULL;
            }
            else {
                sep = "";
                for (std::vector<Value *>::iterator it = array->values.begin(); it != array->values.end(); ++it) {
                    os << sep;
                    _visit(*it);
                    sep = ", ";
                }
                if (strlen(sep)<1) {
                    os << "NULL";
                }
                else {
                    os << "}";
                }
            }
        }
    }

    void visit(Blob *blob) {
        if (dumpFlags&DUMP_FLAG_C_SOURCE) {
            int c, x, *bp = (int*)blob->buf;
            for (x = c = 0; c < blob->size/4; c++) {
                x += *bp++;
            }
            sprintf( (char*)&blobname, "_blob_%llu_size_%x_%x",
                     *((unsigned long long*)blob->buf), \
                     (unsigned int)blob->size, (unsigned int)x);

            os << blobname;

            /*
             * was this data saved already?
             */
            char* bb = blobnamebuffer;

            for (unsigned i = 0 ; i < blobnamebuffersize;
                 i++, bb += strlen(bb)+1) {
                if (strcmp((char*)blobname, bb) == 0)
                {
                    return;
                }
            }

            blobnamebuffer = (char*)realloc( blobnamebuffer,(bb-blobnamebuffer)+
                                     strlen(blobname)+1);

            bb = blobnamebuffer;
            for (unsigned i = 0 ; i < blobnamebuffersize;
                 i++, bb += strlen(bb)+1) {
            }
            memcpy(bb, (void*)&blobname, strlen(blobname)+1);
            blobnamebuffersize++;

            std::ofstream tempstream;
            char newname[1024];
            sprintf((char*)&newname, "%s/%s", write_folder, blobname);

            os_c_course_tables << "unsigned char *" << blobname << " = NULL;\n";
            os_c_include << "extern unsigned char* " << blobname << ";\n";

            tempstream.open(newname);
            tempstream.write(blob->buf, blob->size);
            tempstream.close();
        }
        else
            os << pointer << "blob(" << blob->size << ")" << normal;
    }

    void visit(Pointer *p) {
        if (dumpFlags&trace::DUMP_FLAG_C_SOURCE) {
            if(strcmp(currentargname, "dpy")==0) {
                os << "display";
                return;
            }
            if(strcmp(currentargname, "surface")==0) {
                os << "surface";
                return;
            }

            const char handled_resources[][32] =
            {
               "dest",
               "sync",
               "textures"
            };

            for (int c = 0; c < 3; c++) {
               if(strcmp(currentargname, handled_resources[c]) == 0) {
                  os << handled_resources[c] << "_"  << std::dec
                     << p->value;
                  last_uint_val = p->value;
                  return;
               }
            }

            os << "0x" << std::hex << p->value << std::dec;
        }
        else
            os << pointer << "0x" << std::hex << p->value << std::dec << normal;
    }

    void visit(Repr *r) {
        _visit(r->humanValue);
    }

    void visit(StackFrame *frame) {
        frame->dump(os);
    }

    void visit(Backtrace & backtrace) {
        for (int i = 0; i < backtrace.size(); i ++) {
            visit(backtrace[i]);
            os << "\n";
        }
    }

    void visit(Call *call) {
        CallFlags callFlags = call->flags;

        if (dumpFlags & DUMP_FLAG_C_SOURCE) {
            os << "    ";
            sig = call->sig->name;

            enum callerHandling { Defaultcase };

            const struct
            {
               callerHandling handler;
               char           apiCall[32];
               int            apiCallNameLen;
               char           resName[32];
               char           resType[16];
            } handled_resources[] =
            {
               {Defaultcase, "glCreateProgram", 15, "programs_", "GLuint "},
               {Defaultcase, "glCreateShader", 14, "shader_", "GLuint "},
               {Defaultcase, "glMapBuffer", 11, "dest_", "void* "},
               {Defaultcase, "glMapBufferRange", 16, "dest_", "void* "},
               {Defaultcase, "glFenceSync", 11, "sync_", "GLsync "}
            };

            for (int c = 0; c < sizeof(handled_resources)
                 /sizeof(handled_resources[0]); c++) {
               if (strncmp(call->name(), handled_resources[c].apiCall, 
                           handled_resources[c].apiCallNameLen) == 0 ) {

                  switch (handled_resources[c].handler ) {

                  case Defaultcase:
                  default:
                     sprintf( (char*)&blobname, "%s%d",
                              handled_resources[c].resName, \
                              (unsigned int)call->ret->toUInt());
                     break;
                  }

                  /*
                   * was this data saved already?
                   */
                  char* bb = blobnamebuffer;

                  for (unsigned i = 0 ; i < blobnamebuffersize;
                       i++, bb += strlen(bb)+1) {
                      if (strcmp((char*)blobname, bb) == 0)
                      {
                          goto no_storing;
                      }
                  }

                  blobnamebuffer = (char*)realloc( blobnamebuffer,(bb-blobnamebuffer)+
                                           strlen(blobname)+1);

                  bb = blobnamebuffer;
                  for (unsigned i = 0 ; i < blobnamebuffersize;
                       i++, bb += strlen(bb)+1) {
                  }
                  memcpy(bb, (void*)&blobname, strlen(blobname)+1);
                  blobnamebuffersize++;



no_storing:

                  switch (handled_resources[c].handler ) {
                  default:
                     os << handled_resources[c].resName  << std::dec 
                        << call->ret->toSInt() << " = ";
                     os_c_course_tables << handled_resources[c].resType
                                        << handled_resources[c].resName
                                        << std::dec << call->ret->toUInt() 
                                        << ";\n";
                     os_c_include << "extern " << handled_resources[c].resType
                                  << handled_resources[c].resName << std::dec
                                  << call->ret->toUInt() << ";\n";
                     goto leaveloop;
                  }
               }
            }
leaveloop:;
        }

        if (!(dumpFlags & DUMP_FLAG_NO_CALL_NO)) {
            os << call->no << " ";
        }
        if (dumpFlags & DUMP_FLAG_THREAD_IDS) {
            os << "@" << std::hex << call->thread_id << std::dec << " ";
        }

        if (!dumpFlags & DUMP_FLAG_C_SOURCE) {
            if (callFlags & CALL_FLAG_NON_REPRODUCIBLE) {
                os << strike;
            } else if (callFlags & (CALL_FLAG_FAKE | CALL_FLAG_NO_SIDE_EFFECTS)) {
                os << normal;
            } else {
                os << bold;
            }
        }
        if (dumpFlags&DUMP_FLAG_C_SOURCE)
            os << call->sig->name;
        else
            os << call->sig->name << normal;

        os << "(";
        const char *sep = "";
        for (unsigned i = 0; i < call->args.size(); ++i) {
            os << sep;
            currentargname = call->sig->arg_names[i];
            if (!(dumpFlags & DUMP_FLAG_NO_ARG_NAMES
                  || dumpFlags & DUMP_FLAG_C_SOURCE)) {
                os << italic << call->sig->arg_names[i] << normal << " = ";
            }
            if (call->args[i].value) {
                _visit(call->args[i].value);
            } else {
               os << "?";
            }
            sep = ", ";
        }
        if (dumpFlags&DUMP_FLAG_C_SOURCE)
            os << ");";
        else
            os << ")";

        if (call->ret && !dumpFlags&DUMP_FLAG_C_SOURCE) {
            os << " = ";
            _visit(call->ret);
        }
        
        if (callFlags & CALL_FLAG_INCOMPLETE) {
            os << " // " << red << "incomplete" << normal;
        }
        
        os << "\n";

        if (call->backtrace != NULL) {
            os << bold << red << "Backtrace:\n" << normal;
            visit(*call->backtrace);
        }
        if (callFlags & CALL_FLAG_END_FRAME) {
            os << "\n";
        }
    }
};


void dump(Value *value, std::ostream &os, std::ostream &os2, std::ostream &os3, DumpFlags flags) {
    Dumper d(os, os2, os3, flags);
    value->visit(d);
}

void dump(Call &call, std::ostream &os, std::ostream &os2, std::ostream &os3,DumpFlags flags) {
/*
   if ( strcmp(call.sig->name, "glDrawBuffers") == 0 )
   {
      fprintf(stderr, "glDrawBuffers\n");
   }
*/
    Dumper d(os, os2, os3, flags);
    d.visit(&call);
}


} /* namespace trace */
