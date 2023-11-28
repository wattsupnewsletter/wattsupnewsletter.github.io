#!/usr/bin/env python

import logging
import argparse
import sys
from os.path import exists, basename, splitext
from os import mkdir, listdir

import fitz  # PyMuPDF for image extraction
import pdfminer
from pdfminer.high_level import extract_pages  # XML like PDF document traversal
from yattag.doc import Doc


class InlineElement:
    """Wrapper for inline elements. Contains the parent element and a list of children"""
    def __init__(self, base, children):
        self.base_element = base
        self.children = children

        # We're always going to have at least 1 child element when we're initalising this class
        inline_count = 1
        for i, curr_element in enumerate(self.children):
            j = i + 1
            if j >= len(self.children):
                break

            if curr_element.is_voverlap(self.children[j]):
                inline_count += 1

        self.total_inline = inline_count

    def __str__(self):
        self_string = str(self.base_element) + "\n"

        for child in self.children:
            self_string += ("  " + str(child) + "\n")

        return self_string

def create_campaign_directory(name: str):
    """Creates the directory for a given campaign and needed subdirectories"""
    paths = [
        name,
        name + "/img"
    ]

    for path in paths:
        try:
            mkdir(path)
        except FileExistsError:
            logging.info("Path already exists for %s", path)


def extract_images(in_path: str, out_path: str):
    """Extracts all images from a PDF file and writes them to disk"""

    pdf_doc = fitz.open(in_path)

    for page in range(len(pdf_doc)):
        curr_page = pdf_doc[page]
        image_list = curr_page.get_images()

        if not image_list:
            logging.warning("No images found on page %d", page.number)

        for image in image_list:
            base_img = pdf_doc.extract_image(image[0])
            img_data = base_img["image"]
            img_name = image[7] + ".png"  # The image variable is a tuple containing image data. Index 7 is the name of it in the doc

            with open(out_path + "/img/" + img_name, "wb") as img_file:
                img_file.write(img_data)


def is_element_inline_child(elements: dict, child):
    """Checks if an object is already an inline child of a PDF element"""
    for key in elements:
        if child in elements[key]:
            return True

    return False


def is_ignore_class(obj):
    """Checks if a given object is a class type that should be ignored"""
    match obj.__class__:
        case pdfminer.layout.LTRect | \
             pdfminer.layout.LTCurve | \
             pdfminer.layout.LTLine:
            return True
        case _:
            return False


def serialise_inline_elements(element: InlineElement, doc, tag, text, out_path: str):
    """Turns an InlineElement object into HTML"""
    with tag('div', klass=f"inline-{element.total_inline + 1}"):
        serialise_element(element.base_element, doc, tag, text, out_path)

        i = 0
        while i < len(element.children):
            match element.children[i].__class__:
                case pdfminer.layout.LTFigure:
                    doc.stag('img', src='/' + out_path + '/img/' + element.children[i].name + '.png')
                    i += 1
                    continue
                case pdfminer.layout.LTTextBoxHorizontal:
                    content = element.children[i].get_text().replace('\n', ' ').replace('\t', ' ')
                    i += 1

                    while i < len(element.children) and not element.children[i - 1].is_voverlap(element.children[i]):
                        content += element.children[i].get_text().replace('\n', ' ').replace('\t', ' ')
                        i += 1

                    with tag('p'):
                        text(content)
                case _:
                    i += 1


def serialise_element(element: InlineElement, doc, tag, text, out_path: str):
    """Turns an individual element into HTML"""
    match element.__class__:
        case pdfminer.layout.LTFigure:
            doc.stag('img', src='/' + out_path + '/img/' + element.name + '.png')
        case pdfminer.layout.LTTextBoxHorizontal:
            with tag('p'):
                text(element.get_text().replace('\n', ' ').replace('\t', ' '))
        case pdfminer.layout.LTRect | pdfminer.layout.LTCurve | pdfminer.layout.LTLine:
            logging.info("Skipping class %s", element.__class__)
        case _:
            logging.error("Unsupported element %s", element.__class__)


def serialise_elements(elements: list, out_path):
    """Turns a given list of elements into HTML"""
    doc, tag, text, _line = Doc().ttl()

    for element in elements:
        if element.__class__ == InlineElement:
            serialise_inline_elements(element, doc, tag, text, out_path)
            continue

        serialise_element(element, doc, tag, text, out_path)

    return doc.getvalue() + "\n"


def get_email_footer_index(elements: list):
    """Returns the index of the start of the email footer from a given element list"""

    # There are two images at the bottom of the newsletter. As these two are always going to be there
    # we're going to keep track of a counter which simply lets us know how many images we've run into
    # and an index of where we are in the element list. Once we've hit the second image and the counter
    # is set to two then we know we're at the beginning of the footer
    counter = 0
    index = 0

    for element in reversed(elements):
        if element.__class__ == pdfminer.layout.LTFigure:
            counter += 1

        index += 1

        if counter == 2:
            break

    start_index = len(elements) - index

    if start_index == len(elements):
        return None

    return start_index


def get_newsletter_elements(path: str):
    """Returns a sorted list of elements for a given newsletter"""
    document_elements = []

    for page in extract_pages(path):
        page_elements = list(page)
        inline_elements = {}

        for element in page_elements:
            if is_ignore_class(element):
                continue

            # Skip if the element is already a child
            if is_element_inline_child(inline_elements, element):
                continue

            for _i, curr_element in enumerate(page_elements):
                if element == curr_element:
                    continue

                # Skip the types we don't care about
                if is_ignore_class(curr_element):
                    continue

                # Skip if we have no overlap with the current element
                if not element.is_voverlap(curr_element):
                    continue

                # If there was an overlap but the outer loop element is a text box and the current element is
                # an image then we need to break out of the loop. If we don't we won't get accurate alignment
                # when text is next to an image
                if element.__class__ == pdfminer.layout.LTTextBoxHorizontal and \
                   curr_element.__class__ == pdfminer.layout.LTFigure:
                    break

                if element not in inline_elements:
                    inline_elements[element] = []

                if not is_element_inline_child(inline_elements, curr_element):
                    inline_elements[element].append(curr_element)

        # Sort the page elements so we can append them to the document elements list
        # pdfminer sorts the elements by class type by default which we don't want
        page_elements.sort(reverse=True, key=lambda e: e.y0)
        for element in page_elements:
            # If the current element is a key then we need to add an inline element object to the document
            # elements list
            if element in inline_elements:
                inline_section = InlineElement(element, inline_elements[element])
                document_elements.append(inline_section)
                continue

            # If the current element is an inline child then it will either have already been
            # added to the element list or will be added
            if is_element_inline_child(inline_elements, element):
                continue

            document_elements.append(element)

    footer_index = get_email_footer_index(document_elements)

    return document_elements[0:footer_index]


def create_new_html_page(path: str, content: str):
    """Creates a new HTML file for a newsletter"""
    template = []
    with open("./assets/template.html", "r") as f:
        template = f.readlines()

    article_start_line = 34
    template[article_start_line:article_start_line] = [content]

    with open(path + "/newsletter.html", "w+") as newsletter:
        newsletter.write(''.join(template))


def update_article_index_page(content: str):
    """Updates the index page article tag to contain the newest newsletter"""
    page_lines = []
    article_start = 0
    article_end = 0

    with open("./assets/template.html", "r+") as index_page:
        page_lines = index_page.readlines()

        for i in range(len(page_lines)):
            if '<article>' in page_lines[i]:
                article_start = i

            if '</article>' in page_lines[i]:
                article_end = i

        page_lines = page_lines[0:article_start + 1] + [content] + page_lines[article_end:]

    with open("index.html", "w+") as index_page:
        new_content = ''.join(page_lines)
        index_page.write(new_content)


def get_total_newsletters():
    """Get the total number of newsletters in the assets directory"""
    return len(listdir('newsletters'))


def update_article_list(name: str):
    page_lines = []
    list_start = -1

    with open("newsletterindex.html") as f:
        page_lines = f.readlines()

    for line in range(len(page_lines)):
        if '<ol>' in page_lines[line]:
            list_start = line

    if list_start == -1:
        logging.error("Could not find start of newsletter list")
        sys.exit(-1)

    newsletter_number = str(get_total_newsletters())

    new_post = '<li><a href="/newsletters/' + name + '/newsletter.html">' + 'Newsletter ' + newsletter_number + '</a></li>\n'

    page_lines = page_lines[0:list_start + 1] + [new_post] + page_lines[list_start + 1:]

    with open("newsletterindex.html", "w+") as index_page:
        index_page.write(''.join(page_lines))


def main():
    parser = argparse.ArgumentParser(description='Creates a new HTML page from a provided newsletter PDF file')
    parser.add_argument('-p', '--path', help='Path to the PDF file to create a new page for')

    args = parser.parse_args()
    pdf_path = args.path

    if not exists(pdf_path):
        logging.error("Could not find file %s", pdf_path)
        sys.exit(1)

    logging.basicConfig(level=logging.WARNING)

    base_name = splitext(basename(pdf_path))[0]
    out_path = "newsletters/" + base_name

    create_campaign_directory(out_path)
    extract_images(pdf_path, out_path)

    newsletter_elements = get_newsletter_elements(pdf_path)
    html_blob = serialise_elements(newsletter_elements, out_path)

    create_new_html_page(out_path, html_blob)
    update_article_index_page(html_blob)
    update_article_list(base_name)


if __name__ == '__main__':
    main()
