#!/usr/bin/env python

import logging
from subprocess import run
from os import listdir
from os.path import splitext


def main():
    logging.basicConfig(level=logging.INFO)

    pdf_list = listdir('./assets/newsletters')
    newsletter_list = listdir('newsletters')

    new_newsletters = [pdf for pdf in pdf_list if splitext(pdf)[0] not in newsletter_list]

    if not new_newsletters:
        logging.warning("No new newsletters found")
        return

    for newsletter in new_newsletters:
        logging.info("Creating page for newsletter %s", newsletter)
        run(['python', 'converttopage.py', '-p', './assets/newsletters/' + newsletter])


if __name__ == '__main__':
    main()
