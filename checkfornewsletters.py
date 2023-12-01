#!/usr/bin/env python

import logging
from subprocess import run
from os import listdir


def main():
    logging.basicConfig(level=logging.WARNING)

    pdf_list = listdir('./assets/newsletters')
    newsletter_list = listdir('newsletters')

    new_newsletters = [pdf for pdf in pdf_list if pdf not in newsletter_list]

    for newsletter in new_newsletters:
        logging.info("Creating page for newsletter %s", newsletter)
        run(['python', 'converttopage.py', '-p', './assets/newsletters/' + newsletter])


if __name__ == '__main__':
    main()
