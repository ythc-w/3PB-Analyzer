"""Shared, configurable plots. Display cropping never modifies analysis arrays."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
import json
import math
import textwrap
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import is_color_like, to_hex

DEFAULT_COLORS = {
    'curve': '#225b91', 'fit': '#e78b28', 'offset': '#77834e',
    'peak': '#1b5b99', 'yield': '#d97b18', 'fracture': '#bb3b50',
    'grid': '#c9ced4', 'axes': '#333333', 'text': '#333333',
}
PALETTE = ['#225b91', '#d97b18', '#29866f', '#bb3b50', '#8054a5', '#71833e', '#846145', '#258fa6']

@dataclass
class PlotOptions:
    fit_linestyle: str = '-'
    colors: dict = field(default_factory=lambda: dict(DEFAULT_COLORS))
    overlay_colors: dict = field(default_factory=dict)
    trim_precontact: bool = True
    contact_force_n: float = 0.5
    contact_peak_pct: float = 2.0
    contact_consecutive: int = 3
    context_points: int = 1

    def validate(self):
        if self.fit_linestyle not in ('-', '--'):
            raise ValueError('拟合线型必须为实线 - 或虚线 --。')
        for key in DEFAULT_COLORS:
            if key not in self.colors or not is_color_like(self.colors[key]):
                raise ValueError(f'无效颜色：{key}')
        for name, value in self.overlay_colors.items():
            if not is_color_like(value):
                raise ValueError(f'样本 {name} 的叠加图颜色无效。')
        if not isinstance(self.trim_precontact, bool):
            raise ValueError('trim_precontact 必须为布尔值。')
        for n in (self.contact_force_n, self.contact_peak_pct):
            if not math.isfinite(n) or n < 0:
                raise ValueError('接触阈值必须为非负有限数值。')
        if self.contact_peak_pct > 100:
            raise ValueError('峰值百分比阈值不能超过 100%。')
        if not isinstance(self.contact_consecutive, int) or self.contact_consecutive < 1:
            raise ValueError('连续点数必须为正整数。')
        if not isinstance(self.context_points, int) or self.context_points < 0:
            raise ValueError('接触前保留点数必须为非负整数。')
        return self

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, values):
        values = dict(values)
        values['colors'] = {**DEFAULT_COLORS, **values.get('colors', {})}
        values['colors'] = {k: to_hex(v) for k,v in values['colors'].items()}
        values['overlay_colors'] = {k: to_hex(v) for k,v in values.get('overlay_colors', {}).items()}
        return cls(**values).validate()

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding='utf-8-sig')))

    def save(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')


def display_window(x, y, options, fit_start=None, critical_x=()):
    """Require a sustained positive force before peak to reject isolated noise.

    All known fitted and critical points remain visible even if a high threshold
    requests a later start. This is a display heuristic, not contact measurement.
    """
    options.validate()
    x, y = np.asarray(x), np.asarray(y)
    threshold = max(options.contact_force_n, options.contact_peak_pct * float(np.max(y)) / 100)
    report = {'threshold_n': threshold, 'contact_index': None, 'display_start_index': 0,
              'hidden_points': 0, 'display_start_mm': float(x[0]), 'status': 'disabled'}
    if not options.trim_precontact:
        return 0, report
    count = options.contact_consecutive
    peak = int(np.argmax(y))
    above = y >= threshold
    contact = next((i for i in range(max(0, peak-count+2)) if bool(np.all(above[i:i+count]))), None)
    if contact is None:
        report['status'] = 'no_sustained_contact; full curve retained'
        return 0, report
    start = max(0, contact-options.context_points)
    proposed = start
    if fit_start is not None:
        start = min(start, int(fit_start))
    for px in critical_x:
        if px is not None and math.isfinite(px):
            start = min(start, max(0, int(np.searchsorted(x, px))-1))
    report.update(contact_index=contact, display_start_index=start, hidden_points=start,
                  display_start_mm=float(x[start]),
                  status='cropped; fit/markers protected' if start < proposed else 'cropped')
    return start, report


def result_window(result, debug, options):
    return display_window(debug['x'], debug['y'], options, int(debug['lin_i'][0]),
                          [result.max_force_disp_mm, result.yield_disp_mm, result.fracture_disp_mm])


def fmt(value, digits=3):
    return f'{value:.{digits}f}' if value is not None and math.isfinite(value) else 'NA'


def _axes_style(ax, options):
    c = options.colors
    ax.figure.set_facecolor('white')
    for figure_ax in ax.figure.axes:
        figure_ax.set_facecolor('white')
    ax.grid(False, which='both', axis='both')
    ax.spines[['top', 'right']].set_visible(False)
    for side in ('bottom', 'left'):
        ax.spines[side].set_color(c['axes'])
    # Axes-fraction decoration preserves scientific limits and survives export.
    for end, start in [((1.015, 0), (.975, 0)), ((0, 1.015), (0, .975))]:
        ax.annotate('', xy=end, xytext=start, xycoords='axes fraction',
                    textcoords='axes fraction', annotation_clip=False, clip_on=False,
                    arrowprops=dict(arrowstyle='-|>', color=c['axes'],
                                    lw=ax.spines['bottom'].get_linewidth(),
                                    mutation_scale=11, shrinkA=0, shrinkB=0, clip_on=False))
    ax.tick_params(colors=c['axes'])
    ax.xaxis.label.set_color(c['text']); ax.yaxis.label.set_color(c['text'])
    ax.title.set_color(c['text'])


def make_sample_figure(result, raw, debug, include_fracture_strain, plot_options=None):
    options = (plot_options or PlotOptions()).validate()
    c = options.colors
    x, y = np.asarray(debug['x']), np.asarray(debug['y'])
    start, report = result_window(result, debug, options)
    i, j = int(debug['lin_i'][0]), int(debug['lin_j'][0])

    # Display coordinates are re-zeroed at the first visible point. This is a
    # plotting transformation only; analysis arrays and exported scientific
    # results retain their original analysis coordinates.
    display_zero = float(x[start])
    xd = x - display_zero
    report['display_zero_mm'] = display_zero

    fig = plt.figure(figsize=(12.8, 7.0), dpi=160)
    gs = fig.add_gridspec(2, 2, width_ratios=[2.45, 1.22], height_ratios=[1.08, 2.85],
                         left=.075, right=.98, bottom=.115, top=.93, wspace=.07, hspace=.08)
    ax = fig.add_subplot(gs[:, 0])
    legend_ax = fig.add_subplot(gs[0, 1]); legend_ax.axis('off')
    panel = fig.add_subplot(gs[1, 1]); panel.axis('off')

    ax.plot(xd[start:], y[start:], color=c['curve'], lw=1.9,
            label='Force-displacement', zorder=2)

    # Draw the actual regression line, using display-relative x coordinates.
    xf = np.array([x[i], x[j]])
    xf_display = xf - display_zero
    ax.plot(xf_display, result.stiffness_n_per_mm*xf + result.stiffness_intercept_n,
            color=c['fit'], lw=2.5, ls=options.fit_linestyle, label='Linear fit', zorder=4)

    reference = np.asarray(debug['y_offset'])
    mask = ((x >= x[start]) & np.isfinite(reference)
            & (reference >= min(0, float(y[start:].min())))
            & (reference <= result.max_force_n*1.13))
    if mask.any():
        method = debug.get('yield_method', 'strain')
        if method == 'strain':
            label = f"{100*debug.get('offset_strain', .002):g}% flexural strain offset"
        elif method == 'three_pb':
            off = 100*debug.get('max_displacement_offset_fraction', .002)
            loss = 100*debug.get('stiffness_loss_fraction', 0.0)
            label = f"3PB: {off:g}% max-displacement offset"
            if abs(loss) > 1e-12:
                label += f" + {loss:g}% stiffness loss"
        else:
            label = f"{debug['delta_offset'][0]:g} mm displacement offset"
        ax.plot(xd[mask], reference[mask], '--', color=c['offset'], lw=1.45,
                label=label, zorder=3)

    # Markers use the same display-relative coordinates as the x-axis.
    for label, px, py, marker, key, size in [
        ('Peak',result.max_force_disp_mm,result.max_force_n,'o','peak',165),
        ('Yield',result.yield_disp_mm,result.yield_force_n,'s','yield',68),
        ('Fracture',result.fracture_disp_mm,result.fracture_force_n,'x','fracture',65)]:
        if math.isfinite(px) and math.isfinite(py):
            kwargs = dict(facecolors='none', edgecolors=c[key]) if marker!='x' else dict(color=c[key])
            ax.scatter([px-display_zero],[py],marker=marker,s=size,linewidths=1.7,
                       label=label,zorder=7,**kwargs)

    span=max(float(x[-1]-x[start]), .001)
    ax.set_xlim(-.025*span,float(x[-1]-display_zero)+.045*span)
    ax.set_ylim(min(float(y[start:].min())*1.1,-result.max_force_n*.045),result.max_force_n*1.14)
    ax.set(xlabel='Displacement from display start (mm)', ylabel='Force (N)',
           title='\n'.join(textwrap.wrap(result.sample_id, 48)))
    _axes_style(ax,options)

    legend = legend_ax.legend(*ax.get_legend_handles_labels(),loc='upper left',bbox_to_anchor=(0,1.02),
                             borderaxespad=0,frameon=False,fontsize=9,labelspacing=.48,handlelength=2.8)
    for text in legend.get_texts(): text.set_color(c['text'])

    # Values shown beside the plot follow the displayed x-axis zero. Post-yield
    # displacement is invariant to a horizontal translation.
    def drel(value):
        return value-display_zero if value is not None and math.isfinite(value) else value

    panel.text(0,1.0,'THREE-POINT BENDING',va='top',fontsize=10,weight='bold',color=c['text'])
    rows=[('Peak load',fmt(result.max_force_n)+' N'),
          ('Peak displacement',fmt(drel(result.max_force_disp_mm))+' mm'),
          ('Stiffness',fmt(result.stiffness_n_per_mm)+' N/mm'),
          ('Fit R²',fmt(result.stiffness_r2,4)),
          ('Yield load',fmt(result.yield_force_n)+' N'),
          ('Yield displacement',fmt(drel(result.yield_disp_mm))+' mm'),
          ('Fracture load',fmt(result.fracture_force_n)+' N'),
          ('Fracture displacement',fmt(drel(result.fracture_disp_mm))+' mm'),
          ('Postyield displacement',fmt(result.postyield_disp_mm)+' mm'),
          ('Work to fracture',fmt(result.work_to_fracture_n_mm)+' N·mm')]
    if include_fracture_strain:
        rows.append(('Apparent fracture strain',fmt(result.fracture_strain_pct,2)+'%'))
    for row,(label,value) in enumerate(rows):
        yy=.885-row*.062
        panel.text(0,yy,label,va='top',fontsize=8.9,color=c['text'])
        panel.text(1,yy,value,ha='right',va='top',fontsize=8.9,color=c['text'])

    note=(f"{start} initial rows hidden; displayed x re-zeroed to 0 mm.\n"
          'Original coordinates retained for calculations.') if start else (
          'Full curve displayed; x starts at 0 mm.')
    panel.text(0,.075,note,va='top',fontsize=8,color=c['text'],linespacing=1.45)
    return fig, report


def plot_one_sample(result, raw, debug, out_path, include_fracture_strain, plot_options=None):
    fig, report=make_sample_figure(result,raw,debug,include_fracture_strain,plot_options)
    fig.savefig(out_path,dpi=180)
    plt.close(fig)
    return report


def plot_overlay(results, raw_map, out_path, plot_options=None, debug_map=None):
    options=(plot_options or PlotOptions()).validate()
    fig,(ax,legend_ax)=plt.subplots(1,2,figsize=(12.8,max(7,1.3+.28*len(results))),
                                   gridspec_kw={'width_ratios':[2.45,1.22]})
    legend_ax.axis('off');reports=[]
    for idx,res in enumerate(results):
        raw=raw_map[res.sample_id]
        x=raw['Displacement_mm'].to_numpy(dtype=float);x=x-x[0]
        y=raw['Force_N'].to_numpy(dtype=float)
        if debug_map and res.sample_id in debug_map:
            start,report=result_window(res,debug_map[res.sample_id],options)
        else:
            start,report=display_window(x,y,options,critical_x=[res.max_force_disp_mm,res.yield_disp_mm,res.fracture_disp_mm])
        reports.append({'sample_id':res.sample_id,**report})
        color=options.overlay_colors.get(res.sample_id,PALETTE[idx%len(PALETTE)])
        x_display=x[start:]
        x_aligned=x_display-x_display[0]
        ax.plot(x_aligned,y[start:],lw=1.8,color=color,label='\n'.join(textwrap.wrap(res.sample_id,30)))
    ax.set(title='Force-displacement curves',xlabel='Displacement from display start (mm)',ylabel='Force (N)')
    _axes_style(ax,options)
    leg=legend_ax.legend(*ax.get_legend_handles_labels(),loc='upper left',frameon=False,fontsize=10)
    for t in leg.get_texts():t.set_color(options.colors['text'])
    note=('Contact-based display crop applied per sample.\n' if options.trim_precontact else '')
    note+=('Curves are horizontally aligned to their\nindividual display start (x = 0).\n'
           'Original coordinates are retained for all\ncalculations.')
    legend_ax.text(0,0,note,va='bottom',fontsize=9,color=options.colors['text'])
    fig.tight_layout(pad=2)
    fig.savefig(out_path,dpi=180);plt.close(fig)
    return reports
