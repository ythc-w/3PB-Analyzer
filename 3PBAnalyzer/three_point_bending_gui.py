#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Three-point bending v4: folder scan, per-sample geometry, optional strain."""
from __future__ import annotations
import json
import io
import math
import os
import queue
import threading
import traceback
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from bending_plotting import PlotOptions, make_sample_figure
from plot_settings_dialog import PlotSettingsDialog
from three_point_bending_analysis import (
    parse_nested_csv_root, analyze_one_sample, write_outputs,
    save_run_config,
)

class ThreePointBendingGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('三点弯曲批量分析 v4.3')
        self.geometry('1100x900'); self.minsize(950, 760)
        self.root_dir=tk.StringVar(); self.output_dir=tk.StringVar(); self.metadata_path=tk.StringVar()
        self.thickness=tk.StringVar(); self.span=tk.StringVar(value='7'); self.rate=tk.StringVar(value='3')
        self.include_strain=tk.BooleanVar(value=True)
        self.yield_method=tk.StringVar(value='弯曲应变偏移')
        self.max_disp_offset_pct=tk.StringVar(value='0.2')
        self.stiffness_loss_pct=tk.StringVar(value='0')
        self.strain_offset_pct=tk.StringVar(value='0.2')
        self.status=tk.StringVar(value='请选择总目录，然后扫描样本。')
        self.items=[]; self.scan_report=None; self.scan_key=None; self.busy=False; self.events=queue.Queue()
        self.last_output=None
        self.plot_options=PlotOptions()
        self._ui(); self.after(100,self._poll)
        self.protocol('WM_DELETE_WINDOW', self._close)

    def _ui(self):
        f=ttk.Frame(self,padding=16);f.pack(fill='both',expand=True)
        ttk.Label(f,text='三点弯曲批量分析',font=('Microsoft YaHei UI',18,'bold')).pack(anchor='w')
        ttk.Label(f,text='选择总目录 → 扫描样本 → 补填厚度 → 生成 Excel 和图片').pack(anchor='w',pady=(3,10))
        paths=ttk.LabelFrame(f,text='数据与保存位置',padding=8);paths.pack(fill='x')
        for r,(label,var,action) in enumerate([
            ('样本总目录',self.root_dir,self._choose_root),('结果父目录',self.output_dir,self._output),
            ('参数 CSV（可选）',self.metadata_path,self._metadata)]):
            ttk.Label(paths,text=label,width=18).grid(row=r,column=0,sticky='w',pady=4)
            ttk.Entry(paths,textvariable=var).grid(row=r,column=1,sticky='ew',padx=6)
            ttk.Button(paths,text='选择…',command=action).grid(row=r,column=2)
        paths.columnconfigure(1,weight=1)
        options=ttk.LabelFrame(f,text='尺寸与断裂应变',padding=10);options.pack(fill='x',pady=9)
        ttk.Checkbutton(options,text='计算并输出断裂应变',variable=self.include_strain,command=self._on_strain_toggle).grid(row=0,column=0,columnspan=6,sticky='w')
        for c,(label,var) in enumerate([('默认厚度 h (mm)',self.thickness),('默认跨距 L (mm)',self.span),('加载速率 (mm/min)',self.rate)]):
            ttk.Label(options,text=label).grid(row=1,column=c*2,sticky='w',padx=(0,5),pady=8)
            ttk.Entry(options,textvariable=var,width=12).grid(row=1,column=c*2+1,padx=(0,18))
        ttk.Label(options,text='CSV 没有厚度时可在这里输入；样本厚度不同时，扫描后双击下面的厚度单元格逐个填写。').grid(row=2,column=0,columnspan=6,sticky='w')
        ttk.Label(options,text='断裂应变 εf = 6hδf/L² × 100%；试样长度不参与该公式。').grid(row=3,column=0,columnspan=6,sticky='w',pady=(4,0))
        bar=ttk.Frame(f);bar.pack(fill='x',pady=(1,6))
        self.scan_btn=ttk.Button(bar,text='1. 扫描样本',command=self._scan);self.scan_btn.pack(side='left')
        ttk.Button(bar,text='默认厚度填入空白项',command=self._fill_thickness).pack(side='left',padx=6)
        ttk.Button(bar,text='导出参数 CSV',command=self._save_parameters).pack(side='left',padx=6)
        ttk.Label(f,text='双击可编辑：样本名称、厚度、跨距、试样长度。原始 CSV 路径保留用于核对。').pack(anchor='w')
        table_frame=ttk.Frame(f);table_frame.pack(fill='both',expand=True,pady=5)
        cols=('sample','source','thickness','span','length','rows')
        self.tree=ttk.Treeview(table_frame,columns=cols,show='headings',height=9,selectmode='browse')
        for col,label,width in zip(cols,('样本名称','原始 CSV（相对路径）','厚度 mm','跨距 mm','长度 mm','数据行数'),(160,370,100,100,100,90)):
            self.tree.heading(col,text=label);self.tree.column(col,width=width,minwidth=65,stretch=col in ('sample','source'))
        sb=ttk.Scrollbar(table_frame,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side='left',fill='both',expand=True);sb.pack(side='right',fill='y');self.tree.bind('<Double-1>',self._edit)
        advanced=ttk.LabelFrame(f,text='屈服点设置',padding=8);advanced.pack(fill='x',pady=6)
        ttk.Label(advanced,text='Yield 方法：',width=24).grid(row=0,column=0,sticky='w',pady=3)
        self.yield_combo=ttk.Combobox(advanced,textvariable=self.yield_method,state='readonly',width=28,
                     values=('3PB-Analyzer','弯曲应变偏移'))
        self.yield_combo.grid(row=0,column=1,sticky='w',pady=3)
        self.yield_combo.bind('<<ComboboxSelected>>',lambda e:self._refresh_yield_controls())
        ttk.Label(advanced,text='3PB 最大位移偏移 (%)',width=24).grid(row=1,column=0,sticky='w',pady=3)
        self.max_disp_entry=ttk.Entry(advanced,textvariable=self.max_disp_offset_pct,width=12)
        self.max_disp_entry.grid(row=1,column=1,sticky='w',pady=3)
        ttk.Label(advanced,text='刚度损失 (%)',width=24).grid(row=2,column=0,sticky='w',pady=3)
        self.stiffness_loss_entry=ttk.Entry(advanced,textvariable=self.stiffness_loss_pct,width=12)
        self.stiffness_loss_entry.grid(row=2,column=1,sticky='w',pady=3)
        ttk.Label(advanced,text='弯曲应变偏移 (%)',width=24).grid(row=3,column=0,sticky='w',pady=3)
        self.strain_offset_entry=ttk.Entry(advanced,textvariable=self.strain_offset_pct,width=12)
        self.strain_offset_entry.grid(row=3,column=1,sticky='w',pady=3)
        self._refresh_yield_controls()
        controls=ttk.Frame(f);controls.pack(fill='x',pady=7)
        self.run_btn=ttk.Button(controls,text='2. 开始分析并导出',command=self._run);self.run_btn.pack(side='right')
        ttk.Button(controls,text='打开结果目录',command=self._open).pack(side='right',padx=8)
        ttk.Button(controls,text='绘图设置 / 预览',command=self._plot_settings).pack(side='left',padx=(0,10))
        self.progress=ttk.Progressbar(controls,mode='indeterminate');self.progress.pack(side='left',fill='x',expand=True,padx=(0,20))
        self.log=tk.Text(f,height=5,wrap='word',state='disabled');self.log.pack(fill='x')
        ttk.Label(f,textvariable=self.status,wraplength=1000).pack(anchor='w',pady=(7,0))

    def _on_strain_toggle(self):
        # The checkbox controls the default Yield family, while the user can
        # still select either method manually afterwards.
        self.yield_method.set('弯曲应变偏移' if self.include_strain.get() else '3PB-Analyzer')
        self._refresh_yield_controls()

    def _refresh_yield_controls(self):
        if not hasattr(self,'max_disp_entry'):
            return
        three_pb = self.yield_method.get() == '3PB-Analyzer'
        self.max_disp_entry.configure(state='normal' if three_pb else 'disabled')
        self.stiffness_loss_entry.configure(state='normal' if three_pb else 'disabled')
        self.strain_offset_entry.configure(state='disabled' if three_pb else 'normal')

    @staticmethod
    def _percent(v,label,allow_zero=False,upper=100.0):
        try:n=float(str(v).strip())
        except ValueError:raise ValueError(f'{label}必须为数字。')
        if not math.isfinite(n) or n<0 or (not allow_zero and n<=0) or n>=upper:
            if allow_zero:raise ValueError(f'{label}必须为 0 到 {upper} 之间的有限数值。')
            raise ValueError(f'{label}必须为大于 0 且小于 {upper} 的有限数值。')
        return n

    def _yield_settings(self):
        if self.yield_method.get()=='3PB-Analyzer':
            max_pct=self._percent(self.max_disp_offset_pct.get(),'3PB 最大位移偏移',allow_zero=True)
            loss_pct=self._percent(self.stiffness_loss_pct.get(),'刚度损失',allow_zero=True)
            return 'three_pb',0.002,max_pct/100.0,loss_pct/100.0
        strain_pct=self._percent(self.strain_offset_pct.get(),'弯曲应变偏移',allow_zero=False)
        return 'strain',strain_pct/100.0,0.002,0.0

    def _plot_settings(self):
        if not self.busy:PlotSettingsDialog(self)

    def _preview_plot(self,options,parent):
        if self.busy:raise ValueError('分析进行中，请完成后预览。')
        if not self.items:raise ValueError('请先扫描样本，然后选中需要预览的样本。')
        selected=self.tree.selection()
        idx=int(selected[0]) if selected else 0
        meta,raw=self.items[idx]
        method,offset_strain,max_disp_fraction,loss_fraction=self._yield_settings()
        if method=='strain' and (meta.thickness_mm is None or meta.thickness_mm<=0 or meta.span_mm is None or meta.span_mm<=0):
            raise ValueError('弯曲应变偏移 Yield 需要有效的试样深度/厚度 h 和支撑跨距 L。')
        result,debug=analyze_one_sample(meta,raw,self.include_strain.get(),
            offset_strain=offset_strain,yield_method=method,
            max_displacement_offset_fraction=max_disp_fraction,
            stiffness_loss_fraction=loss_fraction)
        fig,report=make_sample_figure(result,raw,debug,self.include_strain.get(),options)
        from PIL import Image, ImageTk
        import matplotlib.pyplot as plt
        buffer=io.BytesIO();fig.savefig(buffer,format='png',dpi=100);plt.close(fig);buffer.seek(0)
        pic=Image.open(buffer)
        pic.thumbnail((min(1100,self.winfo_screenwidth()-100),min(650,self.winfo_screenheight()-160)))
        window=tk.Toplevel(parent);window.title('绘图预览：'+meta.sample_id)
        window.transient(parent)
        photo=ImageTk.PhotoImage(pic,master=window)
        label=ttk.Label(window,image=photo);label.image=photo;label.pack(padx=8,pady=8)
        ttk.Label(window,text=f"隐藏 {report['hidden_points']} 行；显示起点 {report['display_start_mm']:.3f} mm；阈值 {report['threshold_n']:.3f} N。").pack(pady=(0,8))
        ttk.Button(window,text='关闭预览',command=window.destroy).pack(pady=(0,8))
        window.grab_set()
        window.protocol('WM_DELETE_WINDOW',window.destroy)
        window.bind('<Destroy>',lambda e: parent.grab_set() if e.widget==window and parent.winfo_exists() else None)

    def _choose_root(self):
        p=filedialog.askdirectory(title='选择包含样本文件夹的总目录')
        if p:
            self.root_dir.set(p)
            if not self.output_dir.get():self.output_dir.set(str(Path(p)/'three_point_bending_results'))
    def _output(self):
        p=filedialog.askdirectory(title='选择结果父目录')
        if p:self.output_dir.set(p)
    def _metadata(self):
        p=filedialog.askopenfilename(filetypes=[('CSV','*.csv')])
        if p:self.metadata_path.set(p)
    @staticmethod
    def _number(v, label, optional=False):
        if not str(v).strip() and optional:return None
        try:n=float(v)
        except ValueError:raise ValueError(f'{label}必须为数字。')
        if not math.isfinite(n) or n<=0:raise ValueError(f'{label}必须为大于 0 的有限数值。')
        return n
    def _key(self):return (self.root_dir.get().strip(),self.metadata_path.get().strip(),self.output_dir.get().strip())
    def _message(self,text):
        self.status.set(text);self.log.configure(state='normal');self.log.insert('end',text+'\n');self.log.see('end');self.log.configure(state='disabled')
    def _set_busy(self,v):
        self.busy=v
        for b in (self.scan_btn,self.run_btn):b.configure(state='disabled' if v else 'normal')
        if v:self.progress.start()
        else:self.progress.stop()
    def _scan(self):
        if self.busy:return
        try:
            root=Path(self.root_dir.get().strip());out=Path(self.output_dir.get().strip())
            if not self.root_dir.get().strip() or not root.is_dir():raise ValueError('请选择有效的样本总目录。')
            if not self.output_dir.get().strip():raise ValueError('请选择结果父目录。')
            if root.resolve()==out.resolve() or root.resolve().is_relative_to(out.resolve()):raise ValueError('结果目录不能等于或包含原始数据目录。')
            h=self._number(self.thickness.get(),'厚度',True);span=self._number(self.span.get(),'跨距');rate=self._number(self.rate.get(),'加载速率')
            metadata=Path(self.metadata_path.get()) if self.metadata_path.get().strip() else None
            key=self._key();self._set_busy(True);self._message('正在扫描 CSV…')
            def work():
                try:
                    items, report=parse_nested_csv_root(root,metadata,span,rate,h,None,out)
                    self.events.put(('scanned',(items,report,key)))
                except Exception:self.events.put(('error',traceback.format_exc()))
            threading.Thread(target=work,daemon=True).start()
        except Exception as exc:messagebox.showerror('检查输入',str(exc))
    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i,(m,raw) in enumerate(self.items):
            source=str(Path(m.relative_folder or '')/m.file_name)
            self.tree.insert('', 'end',iid=str(i), values=(m.sample_id,source,m.thickness_mm or '',m.span_mm or '',m.length_mm or '',len(raw)))
    def _edit(self,event):
        if self.busy:return
        row=self.tree.identify_row(event.y);col=self.tree.identify_column(event.x)
        if not row or col not in ('#1','#3','#4','#5'):return
        i=int(row);m,raw=self.items[i];field={'#1':'sample_id','#3':'thickness_mm','#4':'span_mm','#5':'length_mm'}[col]
        label={'sample_id':'样本名称','thickness_mm':'厚度 (mm)','span_mm':'跨距 (mm)','length_mm':'试样长度 (mm)'}[field]
        answer=simpledialog.askstring('编辑样本',f'{m.sample_id}：{label}',initialvalue=str(getattr(m,field) or ''),parent=self)
        if answer is None:return
        try:
            if field=='sample_id':
                value=answer.strip()
                if not value:raise ValueError('样本名称不能为空。')
                if any(j!=i and other.sample_id.casefold()==value.casefold() for j,(other,_) in enumerate(self.items)):raise ValueError('样本名称不能重复。')
            else:value=self._number(answer,label,field!='span_mm')
            self.items[i]=(replace(m,**{field:value}),raw);self._refresh()
        except Exception as exc:messagebox.showerror('输入错误',str(exc))
    def _fill_thickness(self):
        if self.busy:return
        try:
            h=self._number(self.thickness.get(),'默认厚度')
            if not self.items:raise ValueError('请先扫描样本。')
            self.items=[(replace(m,thickness_mm=h) if m.thickness_mm is None else m,raw) for m,raw in self.items]
            self._refresh();self._message('已将默认厚度填入空白项；逐样本已有厚度保留。')
        except Exception as exc:messagebox.showerror('检查厚度',str(exc))
    def _save_parameters(self):
        if self.busy or not self.items:return
        p=filedialog.asksaveasfilename(defaultextension='.csv',initialfile='sample_metadata.csv',filetypes=[('CSV','*.csv')])
        if p:
            import pandas as pd
            pd.DataFrame([dict(relative_path=(Path(m.relative_folder or '')/m.file_name).as_posix(),sample_id=m.sample_id,
                               thickness_mm=m.thickness_mm,span_mm=m.span_mm,length_mm=m.length_mm,
                               loading_rate_mm_min=m.loading_rate_mm_min) for m,_ in self.items]).to_csv(p,index=False,encoding='utf-8-sig')
            self._message('已导出可重复使用的样本参数表。')
    def _run(self):
        if self.busy:return
        try:
            if not self.items:raise ValueError('请先扫描样本，再填写厚度。')
            if self._key()!=self.scan_key:raise ValueError('路径发生变化，请重新扫描。')
            include=self.include_strain.get()
            method,offset_strain,max_disp_fraction,loss_fraction=self._yield_settings()
            if method=='strain':
                missing=[m.sample_id for m,_ in self.items if m.thickness_mm is None or m.thickness_mm<=0 or m.span_mm is None or m.span_mm<=0]
                if missing:raise ValueError('弯曲应变偏移 Yield 需要有效的试样深度/厚度 h 和支撑跨距 L：\n'+', '.join(missing))
            items=list(self.items);report=self.scan_report.copy()
            plot_options=PlotOptions.from_dict(self.plot_options.to_dict())
            out=Path(self.output_dir.get())/datetime.now().strftime('run_%Y%m%d_%H%M%S_%f')
            self._set_busy(True);self._message('正在分析…')
            def work():
                try:
                    out.mkdir(parents=True,exist_ok=False)
                    results=[];raw_map={};debug_map={}
                    for i,(m,raw) in enumerate(items,1):
                        self.events.put(('log',f'[{i}/{len(items)}] {m.sample_id}'))
                        result,debug=analyze_one_sample(m,raw,include,offset_strain=offset_strain,yield_method=method,max_displacement_offset_fraction=max_disp_fraction,stiffness_loss_fraction=loss_fraction)
                        results.append(result);raw_map[m.sample_id]=raw;debug_map[m.sample_id]=debug
                    write_outputs(results,raw_map,debug_map,out,include,plot_options)
                    report.loc[report['status']=='READY','status']='ANALYZED'
                    report.to_csv(out/'scan_report.csv',index=False,encoding='utf-8-sig')
                    save_run_config(items,out,dict(include_fracture_strain=include,yield_method=method,offset_strain=offset_strain,max_displacement_offset_fraction=max_disp_fraction,stiffness_loss_fraction=loss_fraction,plot_options=plot_options.to_dict()))
                    self.events.put(('done',out))
                except Exception:
                    detail=traceback.format_exc()
                    if out.exists():
                        (out/'ERROR.txt').write_text(detail,encoding='utf-8')
                        report.to_csv(out/'scan_report.csv',index=False,encoding='utf-8-sig')
                    self.events.put(('error',detail))
            threading.Thread(target=work,daemon=True).start()
        except Exception as exc:messagebox.showerror('检查输入',str(exc))
    def _poll(self):
        try:
            while True:
                kind,payload=self.events.get_nowait()
                if kind=='scanned':
                    self.items,self.scan_report,self.scan_key=payload;self._refresh();self._set_busy(False)
                    skipped=int((self.scan_report['status']=='SKIPPED').sum())
                    self._message(f'扫描完成：{len(self.items)} 个样本；跳过 {skipped} 个 CSV。请核对厚度后分析。')
                    if skipped:
                        for _,r in self.scan_report[self.scan_report['status']=='SKIPPED'].iterrows():self._message(f"跳过：{r['relative_path']} — {r['reason']}")
                elif kind=='done':
                    self.last_output=payload;self._set_busy(False);self._message(f'完成：{payload}')
                    messagebox.showinfo('分析完成',f'Excel、汇总表和图片已保存：\n{payload}')
                elif kind=='error':
                    self._set_busy(False);self._message(payload);messagebox.showerror('未完成',payload.splitlines()[-1])
                else:self._message(payload)
        except queue.Empty:pass
        self.after(100,self._poll)
    def _open(self):
        p=self.last_output or Path(self.output_dir.get())
        if not p.exists():return
        if os.name=='nt':os.startfile(str(p))
        else:messagebox.showinfo('结果路径',str(p))
    def _close(self):
        if self.busy:
            messagebox.showinfo('分析进行中','请等待本次任务结束后关闭窗口。');return
        self.destroy()

def main():
    ThreePointBendingGUI().mainloop()
if __name__=='__main__':main()
