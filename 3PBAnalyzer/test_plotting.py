"""Plot checks for display re-zeroing and default contact threshold."""
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import three_point_bending_analysis as a
from bending_plotting import PlotOptions, make_sample_figure


def run():
    x=np.linspace(0,1,101)
    y=np.r_[np.zeros(12),np.linspace(.1,25,55),np.linspace(24,10,31),[2,0,0]]
    raw=pd.DataFrame({'Displacement_mm':x,'Force_N':y})
    meta=a.SampleMeta('plot','plot.csv')
    result,debug=a.analyze_one_sample(meta,raw,False,yield_method='three_pb',
                                      max_displacement_offset_fraction=.002,
                                      stiffness_loss_fraction=0.0)
    options=PlotOptions()
    assert np.isclose(options.contact_force_n,.5)
    fig,report=make_sample_figure(result,raw,debug,False,options)
    ax=fig.axes[0]
    curve=ax.lines[0]
    assert np.isclose(curve.get_xdata()[0],0.0)
    assert report['hidden_points']>0
    assert np.isclose(report['display_zero_mm'],debug['x'][report['display_start_index']])
    plt.close(fig)
    print('PASS v4.3 plotting: default 0.5 N threshold and visible x-axis re-zeroed to 0 mm')


if __name__=='__main__':
    run()
