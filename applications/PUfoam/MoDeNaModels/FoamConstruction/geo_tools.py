#!/usr/bin/env python
"""Manipulates .geo input files for gmsh.

Usage:
    geo_tools.py [-h | --help] [-v | --verbose]

Options:
    -h --help     Show this screen.
    -v --verbose  Verbose mode.

@author Pavel Ferkl
"""
from __future__ import print_function
import re
import shutil
import subprocess as sp
import numpy as np
from blessings import Terminal
from docopt import docopt
NAMES = {
    'point': 'Point',
    'line': 'Line',
    'line_loop': 'Line Loop',
    'surface': 'Plane Surface',
    'surface_loop': 'Surface Loop',
    'volume': 'Volume',
    'periodic_surface_X': 'Periodic Surface',
    'periodic_surface_Y': 'Periodic Surface',
    'physical_surface': 'Physical Surface',
    'physical_volume': 'Physical Volume'
}
NAME_LIST = [
    'point',
    'line',
    'line_loop',
    'surface',
    'surface_loop',
    'volume',
    'periodic_surface_X',
    'periodic_surface_Y',
    'physical_surface',
    'physical_volume'
]
def my_find_all(regex, text):
    """My definition of findall. Returns top level group in list."""
    matches = re.finditer(regex, text)
    my_list = []
    for match in matches:
        my_list.append(match.group(0))
    return my_list

def read_geo(geo_file, ignore_point_format=True, plane_surface=True):
    """
    Reads geometry input file for gmsh into dictionary. Based on regular
    expressions. Points can contain optional fourth argument, thus it is better
    to include everything in curly braces. Some geo files use Surface, some
    Plane Surface. You should specify what you want to read.
    """
    with open(geo_file, "r") as text_file:
        text = text_file.read()
        sdat = {}
        rexp = {}
        if ignore_point_format:
            rexp['point'] = r'Point\s?[(][0-9]+[)]\s[=]\s[{](.*?)[}][;]'
        else:
            rexp['point'] = (
                r'Point\s[(][0-9]+[)]\s[=]\s[{]'
                + r'[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)[,]'
                + r'[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)[,]'
                + r'[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)[}][;]'
            )
        rexp['line'] = r'Line\s?[(][0-9]+[)]\s[=]\s[{][0-9]+[,]\s?[0-9]+[}][;]'
        rexp['line_loop'] = (
            r'Line\sLoop\s?[(][0-9]+[)]\s[=]\s[{]([+-]?[0-9]+[,]?\s?)+[}][;]'
        )
        if plane_surface:
            rexp['surface'] = (
                r'Plane\sSurface\s?[(][0-9]+[)]\s[=]\s[{]([0-9]+[,]?\s?)+[}][;]'
            )
        else:
            rexp['surface'] = (
                r'(Surface\s[(][0-9]+[)]\s[=]\s[{]([0-9]+[,]?)+[}][;])'
                + r'(?!.*Physical.*)',
            )
        rexp['physical_surface'] = (
            r'Physical\sSurface\s?[(][0-9]+[)]\s[=]\s[{]([0-9]+[,]?\s?)+[}][;]'
        )
        rexp['surface_loop'] = (
            r'Surface\sLoop\s?[(][0-9]+[)]\s[=]\s[{]([+-]?[0-9]+[,]?\s?)+[}][;]'
        )
        rexp['volume'] = (
            r'Volume\s?[(][0-9]+[)]\s[=]\s[{]([0-9]+[,]?\s?)+[}][;]'
        )
        for key in rexp:
            sdat[key] = my_find_all(rexp[key], text)
        return sdat

def fix_strings(strings):
    """
    Removes negative sign (orientation) from loops. OpenCASCADE has problems
    otherwise.
    """
    for i, line in enumerate(strings):
        strings[i] = re.sub('[-]', '', line)

def save_geo(geo_file, sdat, opencascade=True, char_length=0.1):
    """
    Creates geometry input file for gmsh. Input is a dictionary with prepared
    string lines.
    """
    with open(geo_file, "w") as text_file:
        if opencascade:
            text_file.write('SetFactory("OpenCASCADE");\n')
            text_file.write(
                'Mesh.CharacteristicLengthMax = {0};\n'.format(char_length)
            )
        for key in NAME_LIST:
            if key in sdat:
                for line in sdat[key]:
                    text_file.write("{}\n".format(line))

def extract_data(sdat):
    """Extracts geo data to dictionaries from list of geo strings."""
    edat = {}
    for key in sdat:
        lines = dict()
        for line in sdat[key]:
            part = line.split("(")
            ind = int(part[1].split(")")[0]) # ID of the element
            fraction = line.split("{")
            fraction = fraction[1].split("}")
            fraction = fraction[0].split(",")
            if key == "point": # point data are floats
                # ignore the optional fourth argument (defines mesh coarseness)
                fraction = np.array(fraction[0:3])
                fraction = fraction.astype(np.float)
                for j, number in enumerate(fraction):
                    if abs(number) < 1e-8:
                        fraction[j] = 0
            else: # other data are integers
                fraction = np.array(fraction)
                fraction = np.absolute(fraction.astype(np.int)).tolist()
            lines[ind] = fraction
        edat[key] = lines
    return edat

def collect_strings(edat):
    """Creates lists of geo strings from geo data."""
    sdat = {}
    for key in edat:
        sdat[key] = []
        if key == 'periodic_surface_X':
            for j in edat[key]:
                sdat[key].append(
                    '{0} {{{1}}} = {{{2}}} Translate{{-1,0,0}};'.format(
                        NAMES[key], j[0], j[1]
                    )
                )
        elif key == 'periodic_surface_Y':
            for j in edat[key]:
                sdat[key].append(
                    '{0} {{{1}}} = {{{2}}} Translate{{0,-1,0}};'.format(
                        NAMES[key], j[0], j[1]
                    )
                )
        else:
            for i, j in edat[key].iteritems():
                j = ','.join(str(e) for e in j)
                sdat[key].append('{0} ({1}) = {{{2}}};'.format(
                    NAMES[key], i, j
                ))
    return sdat

def surfaces_in_plane(edat, coord, direction):
    """Finds surfaces that lie completely lie in a plane"""
    points_in_plane = []
    for i, point in edat['point'].iteritems():
        if point[direction] == coord:
            points_in_plane.append(i)
    lines_in_plane = []
    for i, line in edat['line'].iteritems():
        if line[0] in points_in_plane and line[1] in points_in_plane:
            lines_in_plane.append(i)
    line_loops_in_plane = []
    for i, line_loop in edat['line_loop'].iteritems():
        log = True
        for line in line_loop:
            if line not in lines_in_plane:
                log = False
        if log:
            line_loops_in_plane.append(i)
    return line_loops_in_plane

def other_surfaces(surface_loops, surf0, surf1):
    """
    Returns list of boundary surfaces, which are not in surf0 or surf1. Assumes
    that inner surfaces are shared by two volumes. Remove duplicates before
    calling this function.
    """
    all_surfaces = []
    for surface_loop in surface_loops:
        all_surfaces += surface_loop
    count = dict()
    for surface in all_surfaces:
        if surface in count:
            count[surface] += 1
        else:
            count[surface] = 1
    surf = [
        i for i, j in count.items() if j == 1
        and i not in surf0 and i not in surf1
    ]
    return surf

def periodic_surfaces(edat, surfaces, vec, eps=1e-8):
    """
    Returns list of periodic surface pairs in specified direction. Parameter eps
    is used to compare coordinates (floating point numbers).
    """
    surface_points = dict() # point IDs for each boundary surface
    boundary_points = dict() # dictionary with only boundary points
    for surface in surfaces:
        surface_points[surface] = []
        for line in edat['line_loop'][surface]:
            for point in edat['line'][line]:
                if point not in surface_points[surface]:
                    surface_points[surface] += [point]
                if point not in boundary_points:
                    boundary_points[point] = edat['point'][point]
    # sort point IDs so that you can compare later
    for point in surface_points.itervalues():
        point.sort()
    # dictionary with ID of periodic point for each point that has one
    periodic_points = dict()
    for i, point in boundary_points.iteritems():
        for j, secondpoint in boundary_points.iteritems():
            if np.sum(np.abs(point + vec - secondpoint)) < eps:
                periodic_points[i] = j
    psurfs = [] # list of periodic surface pairs (IDs)
    for i, surface in surface_points.iteritems():
        # Try to create surface using IDs of periodic points. Use None if there
        # is no periodic point in specified direction.
        per_surf = [
            periodic_points[point] if point in periodic_points else None
            for point in surface
        ]
        if None not in per_surf:
            per_surf.sort() # sort so you can find it
            # use ID of current surface and find ID of periodic surface
            psurfs.append(
                [
                    i,
                    surface_points.keys()[
                        surface_points.values().index(per_surf)
                    ]
                ]
            )
    return psurfs

def identify_duplicity(edat, key, number, eps=1e-8):
    """
    Core algorithm for removing duplicities. User should call remove_duplicity()
    instead. Parameter eps is used to compare coordinates (floating point
    numbers).
    """
    dupl = dict()
    if number == 'float':
        for i, item1 in edat[key].iteritems():
            for j, item2 in edat[key].iteritems():
                if i != j and i > j and np.sum(np.abs(item1 - item2)) < eps:
                    if i not in dupl:
                        dupl[i] = []
                    dupl[i].append(j)
    elif number == 'integer':
        for i, item1 in edat[key].iteritems():
            for j, item2 in edat[key].iteritems():
                if i != j and i > j and sorted(item1) == sorted(item2):
                    if i not in dupl:
                        dupl[i] = []
                    dupl[i].append(j)
    else:
        raise Exception('number argument must be float or integer')
    return dupl

def remove_duplicit_ids_from_keys(edat, dupl, key):
    """Removes duplicit IDs from IDs of entities."""
    for i in dupl:
        del edat[key][i]

def remove_duplicit_ids_from_values(edat, dupl, key):
    """Removes duplicit IDs from values of entities."""
    for values in edat[key].itervalues():
        for j, value in enumerate(values):
            if value in dupl:
                values[j] = min(dupl[value])

def remove_duplicity(edat, eps=1e-8):
    """
    Removes duplicit points, lines, etc. Parameter eps is used to compare
    coordinates (floating point numbers).
    """
    # points
    dupl = identify_duplicity(edat, 'point', 'float', eps)
    remove_duplicit_ids_from_keys(edat, dupl, 'point')
    remove_duplicit_ids_from_values(edat, dupl, 'line')
    # lines
    dupl = identify_duplicity(edat, 'line', 'integer', eps)
    remove_duplicit_ids_from_keys(edat, dupl, 'line')
    remove_duplicit_ids_from_values(edat, dupl, 'line_loop')
    # line loops
    dupl = identify_duplicity(edat, 'line_loop', 'integer', eps)
    remove_duplicit_ids_from_keys(edat, dupl, 'line_loop')
    remove_duplicit_ids_from_keys(edat, dupl, 'surface')
    remove_duplicit_ids_from_values(edat, dupl, 'surface_loop')
    # there are no duplicit volumes

def move_to_box(infile, wfile, outfile, volumes):
    """
    Moves periodic closed foam to periodic box. Uses gmsh, specifically boolean
    operations and transformations from OpenCASCADE. The result is unrolled to
    another geo file so that it can be quickly read and worked with in the
    follow-up work.
    """
    with open(wfile, 'w') as wfl:
        mvol = max(volumes)
        wfl.write('SetFactory("OpenCASCADE");\n\n')
        wfl.write('Include "{0}";\n\n'.format(infile))
        wfl.write('Block({0}) = {{-1,-1,-1,3,3,1}};\n'.format(mvol + 1))
        wfl.write('Block({0}) = {{-1,-1, 1,3,3,1}};\n'.format(mvol + 2))
        wfl.write('Block({0}) = {{-1,-1, 0,3,3,1}};\n'.format(mvol + 3))
        wfl.write('Block({0}) = {{-1,-1,-1,3,1,3}};\n'.format(mvol + 4))
        wfl.write('Block({0}) = {{-1, 1,-1,3,1,3}};\n'.format(mvol + 5))
        wfl.write('Block({0}) = {{-1, 0,-1,3,1,3}};\n'.format(mvol + 6))
        wfl.write('Block({0}) = {{-1,-1,-1,1,3,3}};\n'.format(mvol + 7))
        wfl.write('Block({0}) = {{ 1,-1,-1,1,3,3}};\n'.format(mvol + 8))
        wfl.write('Block({0}) = {{ 0,-1,-1,1,3,3}};\n'.format(mvol + 9))
        wfl.write('\n')
        wfl.write(
            'zol() = BooleanIntersection'
            + '{{Volume{{1:{0}}};}}'.format(mvol)
            + '{{Volume{{{0}}}; Delete;}};\n'.format(mvol + 1)
        )
        wfl.write(
            'zoh() = BooleanIntersection'
            + '{{Volume{{1:{0}}};}}'.format(mvol)
            + '{{Volume{{{0}}}; Delete;}};\n'.format(mvol + 2)
        )
        wfl.write(
            'zin() = BooleanIntersection'
            + '{{Volume{{1:{0}}}; Delete;}}'.format(mvol)
            + '{{Volume{{{0}}}; Delete;}};\n'.format(mvol + 3)
        )
        wfl.write('Translate{0,0, 1}{Volume{zol()};}\n')
        wfl.write('Translate{0,0,-1}{Volume{zoh()};}\n\n')
        wfl.write(
            'yol() = BooleanIntersection'
            + '{Volume{zol(),zoh(),zin()};}'
            + '{{Volume{{{0}}}; Delete;}};\n'.format(mvol + 4)
        )
        wfl.write(
            'yoh() = BooleanIntersection'
            + '{Volume{zol(),zoh(),zin()};}'
            + '{{Volume{{{0}}}; Delete;}};\n'.format(mvol + 5)
        )
        wfl.write(
            'yin() = BooleanIntersection'
            + '{Volume{zol(),zoh(),zin()}; Delete;}'
            + '{{Volume{{{0}}}; Delete;}};\n'.format(mvol + 6)
        )
        wfl.write('Translate{0, 1,0}{Volume{yol()};}\n')
        wfl.write('Translate{0,-1,0}{Volume{yoh()};}\n\n')
        wfl.write(
            'xol() = BooleanIntersection'
            + '{Volume{yol(),yoh(),yin()};}'
            + '{{Volume{{{0}}}; Delete;}};\n'.format(mvol + 7)
        )
        wfl.write(
            'xoh() = BooleanIntersection'
            + '{Volume{yol(),yoh(),yin()};}'
            + '{{Volume{{{0}}}; Delete;}};\n'.format(mvol + 8)
        )
        wfl.write(
            'xin() = BooleanIntersection'
            + '{Volume{yol(),yoh(),yin()}; Delete;}'
            + '{{Volume{{{0}}}; Delete;}};\n'.format(mvol + 9)
        )
        wfl.write('Translate{ 1,0,0}{Volume{xol()};}\n')
        wfl.write('Translate{-1,0,0}{Volume{xoh()};}\n\n')
    call = sp.Popen(['gmsh', wfile, '-0'])
    call.wait()
    shutil.move(wfile+'_unrolled', outfile)

def create_walls(edat, alpha=0.1):
    """Creates walls."""
    volume_points = dict() # point IDs for each volume
    for volume in edat['surface_loop']:
        volume_points[volume] = []
        for surface in edat['surface_loop'][volume]:
            for line in edat['line_loop'][surface]:
                for point in edat['line'][line]:
                    if point not in volume_points[volume]:
                        volume_points[volume] += [point]
        volume_points[volume].sort()
    centroids = dict() # centroid for each volume
    for volume in edat['surface_loop']:
        total = 0
        for point in volume_points[volume]:
            total += edat['point'][point]
        total /= len(volume_points[volume])
        centroids[volume] = total
    npoints = len(edat['point'])
    nlines = len(edat['line'])
    nsurfaces = len(edat['line_loop'])
    nvolumes = len(edat['surface_loop'])
    for volume in edat['surface_loop'].keys():
        point_map = dict() # mapping of old points to new points
        nvolumes += 1
        edat['surface_loop'][nvolumes] = []
        for point in volume_points[volume]:
            npoints += 1
            edat['point'][npoints] = edat['point'][point] + alpha*(
                centroids[volume] - edat['point'][point])
            point_map[point] = npoints
        for surface in edat['surface_loop'][volume]:
            nsurfaces += 1
            edat['line_loop'][nsurfaces] = []
            for line in edat['line_loop'][surface]:
                nlines += 1
                edat['line'][nlines] = [
                    point_map[edat['line'][line][0]],
                    point_map[edat['line'][line][1]],
                ]
                edat['line_loop'][nsurfaces] += [nlines]
            edat['surface'][nsurfaces] = [nsurfaces]
            edat['surface_loop'][nvolumes] += [nsurfaces]
        edat['volume'][nvolumes] = [nvolumes]
        edat['volume'][volume] += [nvolumes]
    remove_duplicity(edat)

def main():
    """Main subroutine. Organizes workflow."""
    """
    TODO: Fix final structure. GMSH merges two line loops into one when the
    surface has a hole. OpenCASCADE doesn't like it. There are several options:

    1. Don't work with OpenCASCADE. But you must use oriented line loops and
    surface loops. You have to change several functions (e.g., removal of
    duplicity). Implementation is not trivial.

    2. Split line loops and surface loops. Redefine surfaces and volumes with
    holes. How to detect holes?
    """
    term = Terminal()
    fname = 'FoamClosed'
    print(
        term.yellow
        + "Working on file {}.geo.".format(fname)
        + term.normal
    )
    # read Neper foam
    sdat = read_geo(fname + ".geo") # string data
    # Neper creates physical surfaces, which we don't want
    sdat.pop('physical_surface')
    # remove orientation, OpenCASCADE compatibility
    fix_strings(sdat['line_loop'])
    fix_strings(sdat['surface_loop'])
    # save the foam to geo file
    save_geo(fname + "Fixed.geo", sdat)

    # test walls
    edat = extract_data(sdat)
    create_walls(edat)
    sdat = collect_strings(edat)
    save_geo(fname + "Fixed.geo", sdat)
    # exit()
    # end test walls

    # move foam to a periodic box and save it to a file
    move_to_box(
        fname + "Fixed.geo", "move_to_box.geo", fname + "Box.geo",
        range(1, len(sdat['volume']) + 1)
    )
    # read boxed foam
    sdat = read_geo(fname + "Box.geo") # string data
    edat = extract_data(sdat) # extracted data
    # duplicity of points, lines, etc. was created during moving to a box
    remove_duplicity(edat)
    # identification of physical surfaces for boundary conditions
    surf0 = surfaces_in_plane(edat, 0.0, 2)
    if ARGS['--verbose']:
        print('Z=0 surface IDs: {}'.format(surf0))
    surf1 = surfaces_in_plane(edat, 1.0, 2)
    if ARGS['--verbose']:
        print('Z=1 surface IDs: {}'.format(surf1))
    surf = other_surfaces(edat['surface_loop'].itervalues(), surf0, surf1)
    if ARGS['--verbose']:
        print('other boundary surface IDs: {}'.format(surf))
    edat['physical_surface'] = {1:surf0, 2:surf1, 3:surf}
    # identification of periodic surfaces for periodic mesh creation
    edat['periodic_surface_X'] = periodic_surfaces(
        edat, surf, np.array([1, 0, 0])
    )
    if ARGS['--verbose']:
        print(
            'surface IDs periodic in X: {}'.format(edat['periodic_surface_X'])
        )
    edat['periodic_surface_Y'] = periodic_surfaces(
        edat, surf, np.array([0, 1, 0])
    )
    if ARGS['--verbose']:
        print(
            'surface IDs periodic in Y: {}'.format(edat['periodic_surface_Y'])
        )
    # define physical volumes
    edat['physical_volume'] = {1:edat['volume'].keys()}
    # save the final foam
    sdat = collect_strings(edat)
    save_geo(fname + "BoxFixed.geo", sdat)
    print(
        term.yellow
        + "Prepared file {}BoxFixed.geo.".format(fname)
        + term.normal
    )

if __name__ == "__main__":
    ARGS = docopt(__doc__)
    main()
