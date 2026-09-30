"""Tk settings editor. Independent of the scientific analysis implementation."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, colorchooser, filedialog, messagebox
from bending_plotting import PlotOptions, DEFAULT_COLORS, PALETTE

LABELS={'curve':'实验曲线','fit':'线性拟合线段','offset':'屈服偏移线',
        'peak':'峰值标记点','yield':'屈服标记点','fracture':'断裂标记点',
        'axes':'坐标轴与刻度','text':'图中文字'}

class PlotSettingsDialog(tk.Toplevel):
    def __init__(self,parent):
        super().__init__(parent)
        self.owner=parent;self.title('绘图设置');self.geometry('760x630');self.minsize(710,580)
        self.transient(parent);self.grab_set()
        self.options=PlotOptions.from_dict(parent.plot_options.to_dict())
        self.fit=tk.StringVar(value='实线' if self.options.fit_linestyle=='-' else '虚线')
        self.trim=tk.BooleanVar(value=self.options.trim_precontact)
        self.threshold=tk.StringVar(value=str(self.options.contact_force_n))
        self.percent=tk.StringVar(value=str(self.options.contact_peak_pct))
        self.consecutive=tk.StringVar(value=str(self.options.contact_consecutive))
        self.padding=tk.StringVar(value=str(self.options.context_points))
        self.colors=dict(self.options.colors);self.overlay_colors=dict(self.options.overlay_colors)
        self.color_buttons={}
        notebook=ttk.Notebook(self);notebook.pack(fill='both',expand=True,padx=12,pady=12)
        style=ttk.Frame(notebook,padding=16);crop=ttk.Frame(notebook,padding=16);overlay=ttk.Frame(notebook,padding=16)
        notebook.add(style,text='单样本图线型与颜色');notebook.add(crop,text='隐藏接触前数据');notebook.add(overlay,text='叠加图各样本颜色')
        ttk.Label(style,text='线性拟合线段：').grid(row=0,column=0,sticky='w',pady=(0,14))
        ttk.Combobox(style,textvariable=self.fit,values=('实线','虚线'),state='readonly',width=18).grid(row=0,column=1,sticky='w',pady=(0,14))
        for i,(key,label) in enumerate(LABELS.items(),1):
            ttk.Label(style,text=label,width=24).grid(row=i,column=0,sticky='w',pady=5)
            b=tk.Button(style,width=24,command=lambda k=key:self._color(k))
            b.grid(row=i,column=1,sticky='w',pady=5);self.color_buttons[key]=b
        ttk.Label(style,text='图例与指标固定放在曲线外侧。重合标记采用不同大小的空心符号，保持真实坐标。',
                  wraplength=650).grid(row=10,column=0,columnspan=2,sticky='w',pady=12)
        ttk.Checkbutton(crop,text='在图中隐藏接触前的低载荷数据',variable=self.trim).grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,16))
        for row,(label,var,unit) in enumerate([
            ('绝对载荷阈值',self.threshold,'N'),('相对峰值阈值',self.percent,'%'),
            ('连续达到阈值的点数',self.consecutive,'个'),('接触前额外保留点数',self.padding,'个')],1):
            ttk.Label(crop,text=label,width=25).grid(row=row,column=0,sticky='w',pady=10)
            ttk.Entry(crop,textvariable=var,width=14).grid(row=row,column=1,padx=8)
            ttk.Label(crop,text=unit).grid(row=row,column=2,sticky='w')
        ttk.Label(crop,text=(
            '有效阈值 = max（绝对载荷阈值，峰值载荷 × 相对百分比）。\n'
            '默认：max（0.5 N，2% 峰值），连续 3 点达到阈值。\n\n'
            '仅改变显示范围；显示横坐标在首个可见点重新归零，原始数据和分析结果不变。\n'
            '如果阈值会裁掉拟合区间或关键标记，程序会提前显示起点。\n'
            '若没有找到持续接触，显示完整曲线，并写入绘图记录。\n\n'
            '可用“预览选中样本”检查阈值；这是一种接触显示判据，不能替代接触实测。'),
            wraplength=650,justify='left').grid(row=5,column=0,columnspan=3,sticky='w',pady=16)
        ttk.Label(overlay,text='双击样本行选择颜色。此设置作用于所有样本曲线叠加图。').pack(anchor='w',pady=(0,8))
        self.samples=ttk.Treeview(overlay,columns=('sample','color'),show='headings',height=12)
        self.samples.heading('sample',text='样本名称');self.samples.heading('color',text='颜色')
        self.samples.column('sample',width=420);self.samples.column('color',width=170)
        sb=ttk.Scrollbar(overlay,orient='vertical',command=self.samples.yview)
        self.samples.configure(yscrollcommand=sb.set);sb.pack(side='right',fill='y');self.samples.pack(fill='both',expand=True)
        for i,(meta,_) in enumerate(parent.items):
            self.samples.insert('', 'end',iid=str(i),values=(meta.sample_id,self.overlay_colors.get(meta.sample_id,PALETTE[i%len(PALETTE)])))
        self.samples.bind('<Double-1>',self._sample_color)
        if not parent.items:ttk.Label(overlay,text='请先在主界面扫描样本，再设置逐样本颜色。').pack(anchor='w')
        buttons=ttk.Frame(self,padding=(12,0,12,12));buttons.pack(fill='x')
        ttk.Button(buttons,text='读取设置',command=self._load).pack(side='left')
        ttk.Button(buttons,text='保存设置',command=self._save).pack(side='left',padx=5)
        ttk.Button(buttons,text='预览选中样本',command=self._preview).pack(side='left')
        ttk.Button(buttons,text='应用',command=self._apply).pack(side='right')
        ttk.Button(buttons,text='取消',command=self.destroy).pack(side='right',padx=5)
        self._refresh_colors()

    def _refresh_colors(self):
        for key,b in self.color_buttons.items():
            color=self.colors[key];rgb=self.winfo_rgb(color)
            light=sum(a*b for a,b in zip(rgb,(.2126,.7152,.0722)))>32768
            b.configure(bg=color,fg='black' if light else 'white',activebackground=color,text=color)

    def _color(self,key):
        chosen=colorchooser.askcolor(color=self.colors[key],title=LABELS[key],parent=self)[1]
        if chosen:self.colors[key]=chosen;self._refresh_colors()

    def _sample_color(self,event):
        item=self.samples.identify_row(event.y)
        if not item:return
        sample,color=self.samples.item(item,'values')
        chosen=colorchooser.askcolor(color=color,title=sample,parent=self)[1]
        if chosen:self.overlay_colors[sample]=chosen;self.samples.item(item,values=(sample,chosen))

    def _collect(self):
        return PlotOptions(fit_linestyle='-' if self.fit.get()=='实线' else '--',colors=dict(self.colors),
                           overlay_colors=dict(self.overlay_colors),trim_precontact=self.trim.get(),
                           contact_force_n=float(self.threshold.get()),contact_peak_pct=float(self.percent.get()),
                           contact_consecutive=int(self.consecutive.get()),context_points=int(self.padding.get())).validate()

    def _apply(self):
        try:self.owner.plot_options=self._collect();self.owner._message('绘图设置已更新。');self.destroy()
        except Exception as exc:messagebox.showerror('设置错误',str(exc),parent=self)

    def _save(self):
        try:
            options=self._collect()
            path=filedialog.asksaveasfilename(parent=self,defaultextension='.json',initialfile='plot_settings.json',filetypes=[('JSON','*.json')])
            if path:options.save(path)
        except Exception as exc:messagebox.showerror('设置错误',str(exc),parent=self)

    def _load(self):
        path=filedialog.askopenfilename(parent=self,filetypes=[('JSON','*.json')])
        if not path:return
        try:
            o=PlotOptions.load(path);self.colors=dict(o.colors);self.overlay_colors=dict(o.overlay_colors)
            self.fit.set('实线' if o.fit_linestyle=='-' else '虚线');self.trim.set(o.trim_precontact)
            for var,value in [(self.threshold,o.contact_force_n),(self.percent,o.contact_peak_pct),
                              (self.consecutive,o.contact_consecutive),(self.padding,o.context_points)]:var.set(str(value))
            self._refresh_colors()
            for i in self.samples.get_children():
                name=self.samples.item(i,'values')[0]
                self.samples.item(i,values=(name,self.overlay_colors.get(name,PALETTE[int(i)%len(PALETTE)])))
        except Exception as exc:messagebox.showerror('读取失败',str(exc),parent=self)

    def _preview(self):
        try:self.owner._preview_plot(self._collect(),self)
        except Exception as exc:messagebox.showerror('无法预览',str(exc),parent=self)
