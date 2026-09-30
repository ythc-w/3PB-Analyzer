# ThreePointBendingAnalyzer

## 三点弯曲批量分析工具 v2.0.1

本项目是一个基于 Python
的三点弯曲力学测试数据分析工具，用于批量处理力--位移曲线，计算：

-   最大载荷（Maximum Force）
-   刚度（Stiffness）
-   屈服点（Yield Point）
-   断裂点（Fracture Point）
-   断裂前功（Work to fracture）
-   表观弯曲断裂应变（Flexural fracture strain）

## 主要功能

### 1. 数据输入

支持：

-   递归扫描 CSV 文件
-   样本级几何参数管理
-   厚度 h、支撑跨距 L 设置
-   参数 CSV 导入

输入单位要求：

-   Force：N
-   Displacement：mm

## 2. Yield 方法

当前版本包含两种方法：

### 3PB-Analyzer

适用于标准三点弯曲分析：

-   最大位移偏移默认 0.2%
-   刚度损失参数可调

### 弯曲应变偏移法

需要：

-   试样厚度 h
-   支撑跨距 L

默认：

-   strain offset = 0.2%

## 3. GUI 使用

安装依赖：

``` bash
pip install -r requirements.txt
```

启动：

``` bash
python three_point_bending_gui.py
```


基本流程：

1.  选择样本目录
2.  扫描 CSV
3.  检查/填写几何参数
4.  选择 Yield 方法
5.  输出 Excel 和 PNG 图像

## 项目结构

    three_point_bending_analysis.py
        核心分析算法

    three_point_bending_gui.py
        图形界面

    bending_plotting.py
        绘图模块

    plot_settings_dialog.py
        绘图参数设置

    restyle_reference_workbook.py
        Excel 图像重新生成工具

    tests:
        test_analysis.py
        test_plotting.py

## 验证

项目包含：

-   分析回归测试
-   绘图显示测试
-   Excel 输出格式测试

详见：

-   VALIDATION_V2_0_1.txt

## 文献与方法说明

Yield 方法参考：

He Y, Fan X, Li X, Cheng R, Wang B. 3PB-analyzer: A python-based tool
for automated three-point bending analysis. SoftwareX. 2025;30:102177.

详细说明：

-   METHOD_REFERENCE.md
-   README_CN.txt

## License

MIT License
