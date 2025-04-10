#===============================================================================

from datetime import datetime, timezone

#===============================================================================

from lxml import etree

#===============================================================================

from mapmaker.sources.svg.utils import adobe_decode

#===============================================================================

## Run as ``PYTHONPATH='.' python tools/id_to_title.py``
##
__version__ = '1.1.0'


SVG_NS = 'http://www.w3.org/2000/svg'
SVG_GROUP = f'{{{SVG_NS}}}g'

NAMESPACE_MAP = {
    None: 'http://www.w3.org/2000/svg',
    'xlink': 'http://www.w3.org/1999/xlink',
}

#===============================================================================

class SvgTree:
    def __init__(self, svg_tree):
        self.__tree = svg_tree
        self.__root = self.__tree.getroot()
        self.__comments = self.__tree.xpath('/comment()')

    @classmethod
    def from_file(cls, svg_file):
        return cls(etree.parse(svg_file))

    @property
    def root(self):
        return self.__root

    @property
    def comments(self):
        return self.__comments

    def findall(self, pattern):
        return self.__tree.findall(pattern)

    def add_comments(self, comments):
        for comment in comments:
            self.__root.addprevious(comment)

    def add_text_comment(self, comment):
        self.__root.addprevious(etree.Comment(comment))

    def save(self, filename):
        print(f'Writing {filename}')
        self.__tree.write(filename, encoding='utf-8', pretty_print=True,
                          xml_declaration=True)

#===============================================================================

class DeGrouper:
    def __init__(self, svg_tree):
        self.__svg_tree = svg_tree

    def degroup(self):
    #=================
        degrouped = SvgTree(etree.ElementTree(self.__process_element(self.__svg_tree.root)))
        degrouped.add_comments(self.__svg_tree.comments)
        degrouped.add_text_comment(f' Degrouped at {datetime.now(timezone.utc).isoformat()} by {__file__} version {__version__} ')
        return degrouped

    def __process_element(self, element, output=None):
    #=================================================
        if not isinstance(element, etree._Comment):
            if output is None:
                output = etree.Element(element.tag, **element.attrib, nsmap=NAMESPACE_MAP)
            elif element.tag != SVG_GROUP or len(element.attrib) > 0 or len(element) > 1:
                output = etree.SubElement(output, element.tag, attrib=element.attrib)
                if element.text is not None:
                    output.text = element.text
                if element.tail is not None:
                    output.tail = element.tail
            for child in element:
                self.__process_element(child, output)
        return output

#===============================================================================

class Entitler:
    def __init__(self, svg_tree):
        self.__svg_tree = svg_tree

    def title(self):
    #===============
        for xml_element in self.__svg_tree.findall('.//*[@id]'):
            id = xml_element.attrib['id']
            if not id.startswith('SVGID'):
                markup = adobe_decode(id)
                if markup.startswith('.') or markup.startswith('id '):
                    if markup.startswith('id '):
                        tokens = markup.split()
                        if len(tokens) >= 2:
                            markup = f'.id({"_".join(tokens[1:])})'
                elif id.startswith('_'):
                    markup = f'.id({markup.replace(" ", "_")})'
                else:
                    markup = None
                if markup is not None:
                    xml_element.attrib.pop('id', None)
                    title = etree.SubElement(xml_element, 'title')
                    title.text = markup
                    xml_element.insert(0, title)
        self.__svg_tree.add_text_comment(f' Titled at {datetime.now(timezone.utc).isoformat()} by {__file__} version {__version__} ')
        return self.__svg_tree

#===============================================================================

if __name__ == '__main__':
    import argparse
    import sys

    parser = argparse.ArgumentParser(description='Remove extraneous nested groups and add replace `id` markup with <title> elements.')
    parser.add_argument('-v', '--version', action='version', version=__version__)
    parser.add_argument('--no-degroup', action='store_true',
                        help='Replace `id` markup with <title> elements without first removing extraneous nested groups')
    parser.add_argument('--output', metavar='OUTPUT', help='Name of resulting file. Optional')
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite source SVG file')
    parser.add_argument('svg_files', metavar='SVG_FILE(S)', nargs='+',
        help='SVG file(s) to process. The file is overwritten if no OUTPUT is given and --overwrite is set.')
    args = parser.parse_args()

    if args.output is None and args.overwrite is None:
        sys.exit('No output file specified and --overwrite is not set')
    elif args.output is not None and len(args.svg_files) > 1:
        sys.exit('Can only specify --output if processing a single file')

    for svg_file in args.svg_files:
        svg_tree = SvgTree.from_file(svg_file)

        if not args.no_degroup:
            degrouper = DeGrouper(svg_tree)
            svg_tree = degrouper.degroup()

        entitler = Entitler(svg_tree)
        svg_tree = entitler.title()

        svg_tree.save(svg_file if args.output is None else args.output)

#===============================================================================
