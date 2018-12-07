#!/usr/bin/env python2.7
# -*- coding: latin-1 -*-

####
####  bibcloud.py
####  v. 2016-08-01

# Copyright 2015-16 Ecole Polytechnique Federale Lausanne (EPFL)
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

####
####  typical LaTeX setup:
####       \bibliography{../../bibcloud/gen-abbrev,dblp,misc}
####  where
####       gen-abbrev.bib is a generated file in the biblcoud repo (this repo)
####       dblp.bib is self-generated by running bibcloud
####       misc.bib is for the references that are not under DBLP
####
####  usage:  bibcloud.py <main> where <main> is the main latex file (without .tex extension)
####      - run this AFTER pdflatex and BEFORE bibtex
####      - in the $cwd, "dblp-alias.txt" can be used to alias pretty names to full DBLP citations
####          (each line: <pretty> <dblp>)
###       - in the $cwd, "dblp-title.txt" can be use to replace a title (because of capitalization)
####
####  bibcloud does the following:
####     - it scans the <main>.aux file for references from DBLP
####     - maintains a cache of downloaded references in ./bibcloud/*
####     - automatically downloads missing references into the cache from http://dblp.uni-trier.de
####     - automatically generates dblp.bib in the $cwd.  In doing so, it fixes the classic issues associated with bibtex downloads,
####            incl. double {{}} for title
####            generating a per-year specific booktitle for conference proceeedings
####
####  things that you still have to do manually
####     - (optional) dblp-alias.txt -- this is  your naming convention for use within the latex document
####     - (optional) dblp-title.txt -- to fixup titles you don't like
####     - (required) have a gen-abbrev.bib file listed as a bibliography.  This contains the the conference names.  It it is generated by the separate 'makeabbrev.py"
####
####
####  source code control
####     - definitively put dblp.bib under git
####     - no need to put ./bibcloud/* under git



import sys
import os
import xml.etree.ElementTree as ET
import subprocess
import time
import locale


DEBUG = 0

gBibStyle = ""

LOCALFILES = {'cache'   :'.bibcloud/DBLP.xml',
              'alias'   :'dblp-alias.txt',
              'titlefix':'dblp-title.txt'}



DBLP_article = {}

DBLP_fieldlist = {'article':
                      {'title':'double',
                       'journal':'id',
                       'volume':'id',
                       'number':'id',
                       'year':'id',
                       'ee': 'ee',
                       'pages':'id'},
                  'inproceedings':
                      {'title':'double',
                       'year':'id',
                       'pages':'id',
                       'ee': 'ee'},
                  'incollection':
                      {'title':'double',
                       'year':'id',
                       'pages':'id',
                       'ee': 'ee'},
                  'book':
                      {'title':'double',
                       'booktitle':'id',
                       'series':'id',
                       'publisher':'id',
                       'year':'id'}}


# conferences where DBLP does not use an acronym ... normalization is never perfect"
NOACKCONFERENCE = {
    "ACM Conference on Computer and Communications Security" : "ACM Conference on Computer and Communications Security",
    "USENIX Annual Technical Conference, General Track" :  "USENIX Annual Technical Conference",
    "USENIX Annual Technical Conference" : "USENIX",
    "Integrated Network Management" : "Integrated Network Management",
    "Virtual Machine Research and Technology Symposium": "Virtual Machine Research and Technology Symposium",
    "Workshop on I/O Virtualization" : "Workshop on I/O Virtualization",
    "Best of PLDI" : "Best of PLDI",
    "SIGMOD Conference" : "SIGMOD Conference",
    "IEEE Symposium on Security and Privacy" : "IEEE Symposium on Security and Privacy",
    "USENIX Summer" : "USENIX Summer",
    "USENIX Annual Technical Conference, FREENIX Track" : "USENIX Annual Technical Conference, FREENIX Track",
    "Internet Measurement Conference" : "IMC",
    "Internet Measurement Comference" : "IMC",
    "Internet Measurement Workshop" : "IMC",
    "IPDPS Workshops": "IPDPS",
    "USENIX Security Symposium" : "USS",
    "ACM SIGOPS European Workshop" : "ACM SIGOPS European Workshop",
    "3PGCIC" : "threePGCIC",
    "Big Data" :"bigdata",
    "INFLOW@SOSP" :"inflow",
    "IEEE Real Time Technology and Applications Symposium": "rtas",
    "Hot Interconnects": "hoti",
    "Workshop on Hot Topics in Operating Systems" :"hotos",
    "IEEE WISA": "IEEE WISA"
}


WORKSHOPS = ["HotOS","KBNets@SIGCOMM"]

############
### globals
############

ALIAS = {}
REVALIAS = {}
TITLESUB = {}



##### extraction from bibtex .aux file #########
def find_citation(l):
    x = l.find("\\citation{")
    if (x>=0):
        y = l.find("{")
        z = l.find("}",y)
        return l[y+1:z]
        
    x = l.find("\\abx@aux@cite{")
    if (x>=0):
        y = l.find("{")
        z = l.find("}",y)
        return l[y+1:z]
    
    return ""

def load_references(bibname):

    global gBibStyle

    if (not os.path.isfile(bibname)):
        print "FATAL -- File "+bibname+" does not exist"
        sys.exit(1)

    print "bibcloud: parsing ",bibname
    lines = [line.strip() for line in open(bibname)]

    BibSyle = ""
    bibstyleline = [x for x in lines if x.find("\\bibstyle")>=0]
    print "BIBSTYLE is ",bibstyleline
    if len(bibstyleline)==1:
        x = bibstyleline[0].split("{")
        x = x[1].split("}")
        gBibStyle = x[0]
        print "BIBSTYLE (stipped)",gBibStyle


    lines =  [find_citation(line) for line in lines]
    lines  = [c.strip(" ") for c in lines if c != ""]
    lines =  [c.split(",") for c in lines]
    lines =  [y for x in lines for y in x]

    return  sorted(set(lines))


####### strip_comments

def strip_comment(l):
    pos = l.find("%")
    if pos >=0:
        return  l[:pos]
    else:
        return l


def find_revalias(c):
    if REVALIAS.has_key(c):
        return REVALIAS[c]
    else:
        return c



###### update dblp cache ########
def update_dblp(citations,latex_backmap):
    # Processing DBLP files
    num_children = 0
    try:
        tree = ET.parse(LOCALFILES['cache'])
        root = tree.getroot()
        for child in root:
            num_children = num_children+1
            if child.tag == "article" or child.tag=="inproceedings" or child.tag=="book" or child.tag=="incollection" :
                DBLP_article["DBLP:"+child.attrib['key']] = child
    except:
        print "bibcloud: No cache file found...fetching (if the problem persists, delete",LOCALFILES['cache']

    foreign_citations = [c for c in citations if not c.find("DBLP:")==0]
    missing_citations = [c for c in citations if not DBLP_article.has_key(c) and c.find("DBLP:")==0]

    print "bibcloud:",num_children,"cached entries;",len(missing_citations)," missing citations to be fetched;",len(foreign_citations),"handled manually"

    #print "DEBUG MISSING CITATIONS", missing_citations
    #print "FOREIGN CITATIONS",foreign_citations

    if len(missing_citations)==0:
        return

    for c in missing_citations:
        key = c[5:]
        print "bibcloud: fetching",c,"for ",latex_backmap[c]
        print "CURL ... curl https://dblp.uni-trier.de/rec/xml/"+key+".xml"
        os.system("curl https://dblp.uni-trier.de/rec/xml/"+key+ ".xml >.bibcloud/tmp.xml")
        if os.path.getsize(".bibcloud/tmp.xml") >0:

            try:
                if num_children == 0:
                    tree = ET.parse(".bibcloud/tmp.xml")
                    root = tree.getroot()
                else:
                    newtree = ET.parse(".bibcloud/tmp.xml")
                    root.insert(num_children,newtree.getroot()[0])
                num_children = num_children + 1
                print "Updating cache ..."
                tree.write(".bibcloud/DBLP.xml")
            except:
                os.system("mv .bibcloud/tmp.xml .bibcloud/error.xml")
                print "ERROR in XML parsing ... see file ./bibcloud/error.xml"
        else:
                print "FETCH of ",key," failed..."
        time.sleep(2)


########## html_to_bibtex ######
### brutal escaping

HTML_TO_BIB = {
    u'�' : "{\\'e}",
    u'�' : "{\\\"o}",
    u'�' : "{\\\"a}",
    u'�' : "{\\'E}",
    u'�' : "{\\\"u}",
    u"�" : "{\\'e}",
    u"�" : "{\\`e}",
    u"�" : "{\\'a}",
    u"�" : "\\c{c}",
    u"�" : "{\\\"O}",
    u"�" : "\\'{\\i}",
    u"�" : "{\\~{n}}",
    u"�" : "{\\aa}",
    u"�" : "{\\'y}",
    u"\u2248" : "{$\\approx$}"

}


def author_trim(a):
    x = a.split(' ')
    lastword = x[len(x)-1]
    if (lastword[0:3] == '000'):
        print "AUTHOR TRIM",x,lastword
        b =  ' '.join(x[0:len(x)-1])
        print "AUTHOR2 ",b
        return b
    else:
        return a


def html_to_bibtex2(h):

    try:
        return str(h)
    except:
        print "DEBUG: HTML conversion ",h.encode('utf-8')
        x = ""
        for c in h:
            c2 = c.encode('utf-8')
            if HTML_TO_BIB.has_key(c):
                x = x + HTML_TO_BIB[c]
            else:
                x = x + c
        print "DEBUG: HTML conversion ",h.encode('utf-8')," --> ",x.encode('utf-8')
        return x.encode('utf-8')


def html_to_bibtex(s):
    x = html_to_bibtex2(s)
    x = x.replace("&","{\&}")
    return x


def escape_percent(s):
    x = s.find("%")
    if x>=0:
        s2 = s[:x] + "\%" + escape_percent(s[x+1:])
        print "ESCAPING%: ",s,s2
        return s2
    else:
        return s


#complete mess
def escape_percent_amp(s):

    y = s.find("\\&")
    if y>=0:
        print "ESCAPING - skip \\&:",s 
        return s[:y+2] + escape_percent_amp(s[y+2:])

    x = s.find("%")
    y = s.find("&")

    if x>=0 and (x<y or y<0):
        s2 = s[:x] + "\%" + escape_percent_amp(s[x+1:])
        print "ESCAPING%: ",s,s2
        return s2
    elif y>=0:
        s2 = s[:y] + "\&" + escape_percent_amp(s[y+1:])
        print "ESCAPING&: ",s,s2
        return s2
    else:
        return s


DOI_IN_DBLP = ["http://doi.acm.org/","http://doi.ieeecomputersociety.org/","http://dx.doi.org/"]


# warning - can have duplicate tags
def output_doi_ee(url):

    doi = url
    for x in DOI_IN_DBLP:
        doi = doi.replace(x,"")

#    r = "   url = {"+url+"},\n"
    r =""
    if doi == url:
        #print "DOI: ",url
        return r+"  "+"ee = {"+escape_percent(url)+"},\n"
    else:
        return r+"  "+"doi = {"+doi+"},\n"



###################################################
#################### main  ########################
###################################################
# process bib file from ARVG
print "bibcloud: This is bibcloud ... Use at your own risk ... see bibcloud.py source for documentation"


if not os.path.exists(".bibcloud"):
    os.mkdir(".bibcloud")

latex_citations = load_references(sys.argv[1] + ".aux")
print "bibcloud:",len(latex_citations),"unique citations in",sys.argv[1]+".aux"
#print "DEBUG latex_citations",len(latex_citations),"citations = ",latex_citations


if os.path.isfile(LOCALFILES['alias']):
    lines = [line.strip() for line in open(LOCALFILES['alias'])]
    lines = [strip_comment(line) for line in lines]

    for l in lines:
        x = l.split()
        if len(x)>=2 and x[1].find("DBLP:")>=0:
            #print "found alias ",x[0],x[1]
            ALIAS[x[0]] = x[1]
            REVALIAS[x[1]] = x[0]
        elif len(x)>0:
            print "Alias parsing - bad line : ",x
else:
    print "no alias file (",LOCALFILES['alias'],")!"


if os.path.isfile(LOCALFILES['titlefix']):
    lines = [line.strip() for line in open(LOCALFILES['titlefix'])]
    lines = [strip_comment(line) for line in lines]
    for l in lines:
        x = l.split("|")
        if len(x)==2:
            TITLESUB[x[0]] = x[1]
            #print "TITLE substitiution",x[0],x[1]

print "bibcloud:",len(ALIAS),"aliases from",LOCALFILES['alias'],"and",len(TITLESUB),"title substitutions from",LOCALFILES['titlefix']

dblp_citations = [ALIAS[c] if ALIAS.has_key(c) else c for c in latex_citations]
#print "DEBUG dblp_citations",dblp_citations

rev_citations_check = [c for c in latex_citations if REVALIAS.has_key(c)]
if len(rev_citations_check)>0:
    print "bibcloud: FATAL citations cannot be used both aliased and non-aliased",rev_citations_check


latex_backmap  = {key: find_revalias(key)  for key in dblp_citations}
#print "DEBUG latex_backmap=",latex_backmap

update_dblp(dblp_citations,latex_backmap)

# reload DBLP file
tree = ET.parse(LOCALFILES['cache'])
root = tree.getroot()
num_children = 0
for child in root:
    num_children = num_children+1
    if child.tag == "article" or child.tag=="inproceedings" or child.tag=="book" or child.tag=="incollection":
        DBLP_article["DBLP:"+child.attrib['key']] = child



F = open("dblp.bib","w")
F.write("%%% This file is automatically genreated by bibcloud.py\n")
F.write("%%% DO NOT EDIT\n\n\n")

# generate dblp.bib file from XML
for c in dblp_citations:
    if DBLP_article.has_key(c):
        xml = DBLP_article[c]
        if not xml.tag in ["article","inproceedings","book","incollection"]:
            print "bibcloud FATAL unkown tag"
            sys.exit(1)

        fieldlist = DBLP_fieldlist[xml.tag]


        authorlist = [a.text for a in xml if a.tag=="author"]
        authorlist = [html_to_bibtex(a) for a in authorlist]
        authorlist = [author_trim(a) for a in authorlist]
        if gBibStyle == "abbrvnat":
            processedEE = 1
        else:
            processedEE = 0

        if xml.tag =="incollection":
            F.write("\n@"+"inproceedings"+"{"+latex_backmap[c]+",\n")
        else:
            F.write("\n@"+xml.tag+"{"+latex_backmap[c]+",\n")
        F.write("  author = {"+  " and ".join(authorlist) + "},\n")

        for a in xml:
            if fieldlist.has_key(a.tag):
                if fieldlist[a.tag] == 'id':
                    F.write("  "+a.tag+" = {"+html_to_bibtex(a.text)+"},\n")
                elif fieldlist[a.tag] == 'double':
                    if a.tag == "title" and TITLESUB.has_key(a.text):
                        F.write("  "+a.tag+" = {{"+escape_percent_amp(TITLESUB[a.text])+"}},\n")
                    else:
                        F.write("  "+a.tag+" = {{"+escape_percent_amp(html_to_bibtex(a.text))+"}},\n")
                elif fieldlist[a.tag] == 'ee':
                    if processedEE == 0:
                        F.write(output_doi_ee(a.text))
                        processedEE = 1
                else:
                    print "BAD code",fieldlist[a.tag]
                    sys.exit()
        if xml.tag == "inproceedings" or xml.tag=="incollection":
            year = xml.find('year').text[2:]
            booktitle = xml.find('booktitle').text
            if booktitle.find(" ") >0 or booktitle == "3PGCIC" or booktitle == "INFLOW@SOSP":
                if NOACKCONFERENCE.has_key(booktitle):
                    booktitle = NOACKCONFERENCE[booktitle]
                    if booktitle.find(" ")>0:
                        F.write("  booktitle = \""+booktitle+"\",\n")
                    else:
                        F.write("  booktitle = "+booktitle+year+",\n")
                else:
                    print "WARNING -- Unknown conference",booktitle
                    F.write("  booktitle = \""+booktitle+"\",\n")
                    # sys.exit(1)
            else:
                F.write("  booktitle = "+booktitle+year+",\n")

            if (booktitle in WORKSHOPS) or (xml.tag=="incollection") : 
                F.write("  keywords = {workshop},\n")
                print booktitle,"in workshop!",c

        if c != latex_backmap[c]:
             F.write("  bibsource = {DBLP alias: "+c+"}\n")
        F.write("}\n")

print "bibcloud: done"






