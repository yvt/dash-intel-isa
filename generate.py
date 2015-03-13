#!/usr/bin/env python3.4

import os, re, sqlite3, shutil, sys, getopt, PyPDF2, tempfile, atexit, subprocess, html
from PIL import Image, ImageMath, ImageChops
# from bs4 import BeautifulSoup, NavigableString, Tag 

derived_dir = os.path.join(os.path.dirname(__file__), "derived")

docset_dir = os.path.join(os.path.dirname(__file__), "intel-isa.docset")

os.makedirs(derived_dir, exist_ok=True)
os.makedirs(os.path.join(docset_dir, "Contents", "Resources", "Documents"), exist_ok=True)

# parse args
def write_usage():
    print(
        "USAGE: generate.py [-s gs|pass|index]... [-g gs] {-i InputPDFFile.pdf}..."
        )
    sys.exit(2)

GHOSTSCRIPT = os.getenv("GHOSTSCRIPT")
pdf_paths = []
skipped_pass = set()
try:
    opts, args = getopt.getopt(sys.argv[1:], "hg:i:s:")
except getopt.GetoptError as err:
    print(err)
    write_usage()
for o, a in opts:
    if o == "-h":
        write_usage()
    elif o == "-g":
        GHOSTSCRIPT = a
    elif o == "-i":
        pdf_paths.append(a)
    elif o == "-s":
        skipped_pass.add(a)
    else:
        assert False, "unhandlded option"

GHOSTSCRIPT = GHOSTSCRIPT or "gs"
GHOSTSCRIPT = shutil.which(GHOSTSCRIPT)

if not GHOSTSCRIPT:
    print("gs was not found.")
    sys.exit(1)

if len(pdf_paths) == 0:
    print("pdf path is not specified.")
    sys.exit(1)
for pdf_path in pdf_paths:
    if not os.path.exists(pdf_path):
        print("pdf path %s does not exist." % pdf_path)
        sys.exit(1)


# process PDFs

instruction_wrapper = re.compile(r'.*Instructions *\(.*[A-Z].*-.*[A-Z].*\).*')
instruction_title = re.compile(r'([0-9A-Zchn/ ]{1,}[0-9A-Zchn/]) *(?:—|-) *(.*) *')

out_pages = []
out_page_map = {}
all_insts = []
page_names = {}

def image_path_for_pdf(pdf_name):
    return os.path.join(derived_dir, pdf_name + "-%d.png")
def image_path_for_pdf_page(pdf_name, page_num):
    return image_path_for_pdf(pdf_name) % page_num

for pdf_path in pdf_paths:
    pdf_file_name = os.path.basename(pdf_path)
    pdf_name = pdf_file_name[0:-4]
    # pdf_tmp_file_name = os.path.join(derived_dir, pdf_file_name)
    # shutil.copy(pdf_path, pdf_tmp_file_name)

    insts_of_pdf = []

    print("%s: reading" % pdf_name)

    with open(pdf_file_name, mode="rb") as pdf_stream:
        pdf_reader = PyPDF2.PdfFileReader(pdf_stream, strict=False)
        outline = pdf_reader.getOutlines()

        page_map = {}
        for page_num in range(0, pdf_reader.getNumPages()):
            page_map[id(pdf_reader.getPage(page_num)["/Contents"])] = page_num + 1

        end_page = pdf_reader.getNumPages()

        def scan_instructions(node):
            for item in node:
                match = instruction_title.match(item.title)
                if match:
                    inst_joined = match.group(1)
                    description = match.group(2)
                    page = item.page.getObject()["/Contents"]
                    page_num = page_map[id(page)]
                    print(" - %s (%s) at page %s" % (inst_joined, description, page_num))
                    inst = {
                        'pdf_name': pdf_name,
                        'page_num': page_num,
                        'inst_joined': inst_joined,
                        'description': description
                    }
                    insts_of_pdf.append(inst)
                else:
                    print(" + [UNMATCHED] %s" % item.title)

        scan_state = 0

        def scan_outline(node):
            scan_state = 0
            # 0:  find instructions
            # 1:  found instructions
            # 2:  find the first page after instructions
            for i in range(0, len(node)):
                item = node[i]
                if isinstance(item, list):
                    if scan_state == 1:
                        scan_instructions(item)
                        scan_state = 2
                    else:
                        scan_outline(item)
                else:
                    title = item.title
                    if scan_state == 0 and instruction_wrapper.match(title):
                        scan_state = 1
                    elif scan_state == 2:
                        end_page = page_map[item.page.getObject()["/Contents"]] - 1
                        return
                    else:
                        scan_state = 0

        print("%s: scanning outline")
        scan_outline(outline)

    print("%s: last page number of instructions = %d" % (pdf_name, end_page))

    if len(insts_of_pdf) == 0:
        print("%s: NO INSTRUCTIONS FOUND! skipping." % pdf_name)
        continue

    print("%s: organizing" % pdf_name)

    insts_of_pdf.sort(key=lambda inst:inst['page_num'])
    if insts_of_pdf[-1]['page_num'] > end_page:
        print("%s: WARNING: start page of the last instruction (%d) "
            "is after estimated last page of all instructions (%d)" % (pdf_name, insts_of_pdf[-1]['page_num'], end_page))
        end_page = insts_of_pdf[-1]['page_num']

    for i in range(0, len(insts_of_pdf)):
        inst = insts_of_pdf[i]

        inst_start_page = inst['page_num']
        if i == len(insts_of_pdf) - 1:
            inst_end_page = end_page
        else:
            inst_end_page = insts_of_pdf[i + 1]['page_num'] - 1
        insts = [iname.strip() for iname in inst['inst_joined'].split("/")]

        out_page_key = (inst['pdf_name'], inst_start_page, inst_end_page)
        if not out_page_key in out_page_map:
            page_name = "_".join(insts)
            if page_name in page_names:
                page_names[page_name] += 1
                page_name += "_%d" % page_names[page_name]
            else:
                page_names[page_name] = 1

            out_page_map[out_page_key] = len(out_pages)
            out_pages.append({
                'key': out_page_key, 
                'title': inst['inst_joined'], 
                'description': inst['description'],
                'name': page_name
            })
        page_id = out_page_map[out_page_key] 

        description = inst['description']
        for iname in insts:
            all_insts.append({
                'name': iname,
                'start_page': inst_start_page,
                'end_page': inst_end_page,
                'description': description,
                'page_id': page_id,
                'dupe': False
            })
            print(" - %s: %s" % (iname, out_pages[page_id]))

    if "gs" in skipped_pass:
        print("%s: NOT rendering to PNG (skipped)" % pdf_name)
    else:
        print("%s: rendering to PNG" % pdf_name)
        if subprocess.call([GHOSTSCRIPT, "-sDEVICE=png16m", "-r600", "-dDownScaleFactor=4", 
            "-sOutputFile=%s" % image_path_for_pdf(pdf_name), "-dNOPAUSE", "-dBATCH", pdf_file_name]) != 0:
            print("errored while processing %s." % pdf_file_name)
            sys.exit(3)

if "pages" in skipped_pass:
    print("-- NOT generating pages (skipped)")
else:
    print("-- generating pages")

    crop_margin_left = 80
    crop_margin_top = 130
    crop_margin_right = 100
    crop_margin_bottom = 160

    with open("template.html", "r") as f:
        template = f.read()

    for page_id, out_page in enumerate(out_pages):
        (pdf_name, inst_start_page, inst_end_page) = out_page['key']
        print("%d: generating image (%s)" % (page_id, out_page['title']))

        images = [Image.open(image_path_for_pdf_page(pdf_name, i)) 
            for i in range(inst_start_page, inst_end_page + 1)]

        newImages = []
        for i, image in enumerate(images):
            (w, h) = image.size

            image = image.crop((crop_margin_left, crop_margin_top, 
                w - crop_margin_right, h - crop_margin_bottom))

            (w, h) = image.size

            # Auto crop
            contentsMask = ImageChops.invert(image.convert('L'))
            contentsBounds = contentsMask.getbbox()
            if contentsBounds is None:
                continue

            (boundX1, boundY1, boundX2, boundY2) = contentsBounds
            boundX1 = 0
            boundX2 = w
            boundY1 = max(0, contentsBounds[1] - 15)
            boundY2 = min(h, contentsBounds[3] + 15)

            image = image.crop((boundX1, boundY1, boundX2, boundY2))
            newImages.append(image)

        images = newImages
        
        # check image size
        imageWidth = min(image.size[0] for image in images)
        if any(imageWidth != image.size[0] for image in images):
            print("%d: WARNING: image width differs" % page_id)
        imageHeight = sum(image.size[1] for image in images)

        # draw image
        outImage = Image.new(images[0].mode, (imageWidth, imageHeight))

        y = 0
        for image in images:
            outImage.paste(image, (0, y))
            y += image.size[1]

        # palettize
        outImage = outImage.convert('P', palette=Image.ADAPTIVE, colors=16)

        # save
        outImage.save(os.path.join(docset_dir, "Contents", "Resources", "Documents", "I-" + out_page['name'] + ".png"))

        # write HTML
        page_html = template.replace("%TITLE%", html.escape(out_page['title']))
        page_html = page_html.replace("%DESCRIPTION%", html.escape(out_page['description']))
        page_html = page_html.replace("%NAME%", html.escape(out_page['name']))

        with open(os.path.join(docset_dir, "Contents", "Resources", "Documents", "P-" + out_page['name'] + ".html"), "w") as f:
            f.write(page_html)


if "index" in skipped_pass:
    print("-- NOT generating index (skipped)")
else:
    print("-- generating index")

    db = sqlite3.connect(docset_dir + '/Contents/Resources/docSet.dsidx')
    cur = db.cursor()

    try: cur.execute('DROP TABLE searchIndex;')
    except: pass
    cur.execute('CREATE TABLE searchIndex(id INTEGER PRIMARY KEY, name TEXT, type TEXT, path TEXT);')
    cur.execute('CREATE UNIQUE INDEX anchor ON searchIndex (name, type, path);')

    docpath = docset_dir + '/Contents/Resources/Documents'

    inst_map = {}
    for inst in all_insts:
        inst_name = inst['name']
        if inst_name in inst_map:
            inst['dupe'] = True
            inst_map[inst_name][0]['dupe'] = True
        else:
            inst_map[inst_name] = [inst]

    for inst in all_insts:
        out_page = out_pages[inst['page_id']]

        inst_name = inst['name']

        if True or inst['dupe']:
            inst_name += " — " + inst['description']

        cur.execute(R'INSERT OR IGNORE INTO searchIndex(name, type, path) VALUES (?,?,?)', 
            (inst_name, 'Instruction', "P-" + out_page['name'] + ".html"))

    db.commit()
    db.close()
