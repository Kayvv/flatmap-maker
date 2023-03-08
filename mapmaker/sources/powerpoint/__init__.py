#===============================================================================
#
#  Flatmap viewer and annotation tools
#
#  Copyright (c) 2019 - 2022  David Brooks
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#===============================================================================

from __future__ import annotations
from io import BytesIO, StringIO

#===============================================================================

from mapmaker.flatmap.feature import Feature
from mapmaker.flatmap.layers import FEATURES_TILE_LAYER, MapLayer
from mapmaker.settings import settings
from mapmaker.utils import log, pathlib_path, TreeList

from .. import MapSource, RasterSource

from .powerpoint import Powerpoint, Slide
from .svgutils import SvgFromShapes

# Exports
from .powerpoint import Slide

#===============================================================================

def update_label(feature):
    if feature.properties.get('label') is None:
        feature.properties['label'] = ''
    if ((name := feature.properties.get('name', '')) != ''
     and name.lower() == feature.properties['label'].lower()):
        name = ''
    if feature.models and feature.properties['label'] != '':
        feature.properties['label'] += f' ({feature.models})'
    if name not in ['', None]:
        feature.properties['label'] += f'\n{name}'

#===============================================================================

class PowerpointLayer(MapLayer):
    def __init__(self, source: PowerpointSource, id: str, slide: Slide, slide_number: int):
        if source.source_range is None:
            exported = slide_number == 1
        else:
            exported = slide_number == source.source_range[0]
        super().__init__(id, source, exported=exported)
        self.__slide = slide
        self.__slide_number = slide_number

    @property
    def slide(self):
        return self.__slide

    @property
    def slide_number(self):
        return self.__slide_number

    def process(self):
    #=================
        shapes = self.__slide.process(self.flatmap.annotator)

        features = self.__process_shape_list(shapes)
        self.add_features('Slide', features, outermost=True)

        if settings.get('functionalConnectivity', False):
            for feature in self.features:
                if (feature.property('shape-type') == 'connection'
                and feature.property('fc-class') in ['FC_CLASS.NEURAL', 'FC_CLASS.VASCULAR']):
                    self.source.flatmap.connection_set.add(
                        feature.properties['shape-id'],
                        feature.properties['kind'],
                        feature.geojson_id)
                else:
                    update_label(feature)

    def __process_shape_list(self, shapes: TreeList) -> list[Feature]:
    #=================================================================
        features = []
        for shape in shapes[1:]:
            if isinstance(shape, TreeList):
                group_features = self.__process_shape_list(shape)
                grouped_feature = self.add_features('Group', group_features)
                if grouped_feature is not None:
                    features.append(grouped_feature)
            else:
                properties = shape.properties
                self.source.check_markup_errors(properties)
                if 'tile-layer' not in properties:
                    properties['tile-layer'] = FEATURES_TILE_LAYER   # Passed through to map viewer
                if 'error' in properties:
                    pass
                elif 'invisible' in properties:
                    pass
                elif 'path' in properties:
                    pass
                elif properties.get('exclude', False):
                    pass
                else:
                    feature = self.flatmap.new_feature(shape.geometry, properties)
                    features.append(feature)
        return features

#===============================================================================

class PowerpointSource(MapSource):
    def __init__(self, flatmap, id, source_href, source_kind='slides', source_range=None,
                 SlideClass=Slide, slide_options=None):
        super().__init__(flatmap, id, source_href, source_kind, source_range=source_range)
        self.__powerpoint = Powerpoint(id, source_href, source_kind, SlideClass=SlideClass, slide_options=slide_options)
        self.bounds = self.__powerpoint.bounds   # Sets bounds of MapSource
        self.__slides = self.__powerpoint.slides
        self.__shape_filter = slide_options.get('shape_filter') if slide_options is not None else None

    @property
    def transform(self):
        return self.__powerpoint.transform

    def process(self):
    #=================
        if self.source_range is None:
            slide_numbers = range(1, len(self.__slides)+1)
        else:
            slide_numbers = self.source_range
        for slide_number in slide_numbers:
            # Skip slides not in the presentation
            if slide_number < 1 or slide_number >= (len(self.__slides) + 1):
                continue
            slide = self.__slides[slide_number - 1]
            if slide_number == 1 and len(slide_numbers) == 1:
                id = self.id
            else:
                id = f'{self.id}/{slide.id}'
            slide_layer = PowerpointLayer(self, id, slide, slide_number)
            log(f'Slide {slide_number}, {slide_layer.id}')
            if settings.get('saveDrawML'):
                with open(self.flatmap.full_filename(f'{slide_layer.id}.xml'), 'w') as xml:
                    xml.write(slide.pptx_slide.element.xml)
            slide_layer.process()
            self.add_layer(slide_layer)
        if self.kind == 'base' and self.__shape_filter is not None:
            # Processing has added shapes to the filter so now create it
            # so it can be used by subsequent layers
            self.__shape_filter.create_filter()

    def get_raster_source(self):
    #===========================
        if self.kind == 'base':  # Only rasterise base source layer
            return RasterSource('svg', self.__get_raster_data)

    def __get_raster_data(self):
    #===========================
        svg_maker = SvgFromShapes()                                      ## Options
        svg_maker.set_transform(self.__powerpoint)
        for slide in self.__powerpoint.slides:
            svg_maker.add_slide(slide, base_slide=(self.kind=='base'))   ## Options

        # slides to SVG is simply slide_to_svg for all slides in the PPT, using the GLOBAL svg shape filter
        # Do we need a local, secondary filter??
        # PowerpointSource.__slides is the list of PPTX Slide objects
        # Use slide number to access local FCSlideLayer (which has a svg_filter(shape) method??)

        ## Have option to keep intermediate SVG??
        svg = StringIO()
        svg_maker.save(svg)
        svg_bytes = svg.getvalue().encode('utf-8')
        svg.close()

        if settings.get('saveSVG', False):
            svg_file = pathlib_path(self.source_href).with_suffix('.raster.svg')
            with open(svg_file, 'wb') as fp:
                fp.write(svg_bytes)
                log.info(f'Saved intermediate SVG as {svg_file}')

        svg_data = BytesIO(svg_bytes)
        svg_data.seek(0)
        return svg_data

#===============================================================================
