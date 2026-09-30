#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Redraw ALL six figures in an already-corrected reference workbook.

This utility does NOT swap model/O and does NOT edit workbook cells.
python restyle_reference_workbook.py --input corrected.xlsx --output styled.xlsx
"""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import argparse
import posixpath
import xml.etree.ElementTree as ET
import pandas as pd
from three_point_bending_analysis import parse_workbook, analyze_one_sample
from bending_plotting import PlotOptions, plot_one_sample, plot_overlay

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}

def related_path(owner,target):
    return target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(owner),target))

def relationships(parts,owner):
    name=posixpath.join(posixpath.dirname(owner),'_rels',posixpath.basename(owner)+'.rels')
    return {e.attrib['Id']:related_path(owner,e.attrib['Target']) for e in ET.fromstring(parts[name])}

def embed_figures(source,output,plots):
    """Replace PNG bytes and drawing extents only; preserve all worksheet XML."""
    with ZipFile(source) as z:
        parts={name:z.read(name) for name in z.namelist()}
    wbrels=relationships(parts,'xl/workbook.xml')
    workbook=ET.fromstring(parts['xl/workbook.xml'])
    updated=[]
    for sheet in workbook.find('s:sheets',NS):
        name=sheet.attrib['name']
        if name not in plots:continue
        sheetpath=wbrels[sheet.attrib['{'+NS['r']+'}id']]
        sheetdoc=ET.fromstring(parts[sheetpath])
        drawing=sheetdoc.find('s:drawing',NS)
        if drawing is None:raise ValueError(f'{name}: no existing drawing')
        drawingpath=relationships(parts,sheetpath)[drawing.attrib['{'+NS['r']+'}id']]
        doc=ET.fromstring(parts[drawingpath]);blips=doc.findall('.//a:blip',NS)
        if len(blips)!=1:raise ValueError(f'{name}: expected one embedded plot')
        imagepath=relationships(parts,drawingpath)[blips[0].attrib['{'+NS['r']+'}embed']]
        if not imagepath.endswith('.png'):raise ValueError('Expected PNG workbook plot.')
        parts[imagepath]=Path(plots[name]).read_bytes()
        for elem in doc.iter():
            if elem.tag.endswith('}ext') and 'cx' in elem.attrib:
                elem.set('cx',str(1440*9525));elem.set('cy',str(round(1440*7/12.8*9525)))
        parts[drawingpath]=ET.tostring(doc,encoding='utf-8',xml_declaration=True)
        updated.append(name)
    if set(updated)!=set(plots):raise ValueError('Some sample images were not found in the workbook.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(output,'w',ZIP_DEFLATED) as z:
        for name,data in parts.items():z.writestr(name,data)
    return updated

def restyle(source,output,settings=None,yield_method="three_pb",max_disp_offset_pct=.2,stiffness_loss_pct=0.0,strain_offset_pct=.2):
    if source.resolve()==output.resolve():raise ValueError('Choose a separate output file.')
    if output.exists():raise FileExistsError('Output already exists; choose a new filename.')
    settings=(settings or PlotOptions()).validate()
    plotdir=output.parent/(output.stem+'_plots');plotdir.mkdir(parents=True,exist_ok=True)
    items=parse_workbook(source,7,3)
    results=[];rawmap={};debugmap={};plots={};reports=[]
    for meta,raw in items:
        res,debug=analyze_one_sample(
            meta,raw,True,
            yield_method=yield_method,
            offset_strain=strain_offset_pct/100.0,
            max_displacement_offset_fraction=max_disp_offset_pct/100.0,
            stiffness_loss_fraction=stiffness_loss_pct/100.0,
        )
        path=plotdir/(meta.sample_id+'_force_displacement.png')
        report=plot_one_sample(res,raw,debug,path,True,settings)
        results.append(res);rawmap[res.sample_id]=raw;debugmap[res.sample_id]=debug
        plots[res.sample_id]=path;reports.append(dict(sample_id=res.sample_id,**report))
    plot_overlay(results,rawmap,plotdir/'all_samples_overlay.png',settings,debugmap)
    settings.save(plotdir/'plot_settings.json')
    pd.DataFrame(reports).to_csv(plotdir/'plot_display_report.csv',index=False,encoding='utf-8-sig')
    print('Updated:',', '.join(embed_figures(source,output,plots)))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--plot-settings')
    parser.add_argument('--yield-method',choices=['three_pb','strain'],default='three_pb')
    parser.add_argument('--max-displacement-offset-pct',type=float,default=.2)
    parser.add_argument('--stiffness-loss-pct',type=float,default=0.0)
    parser.add_argument('--strain-offset-pct',type=float,default=.2)
    args=parser.parse_args()
    restyle(Path(args.input),Path(args.output),
            PlotOptions.load(args.plot_settings) if args.plot_settings else None,
            args.yield_method,args.max_displacement_offset_pct,args.stiffness_loss_pct,args.strain_offset_pct)
