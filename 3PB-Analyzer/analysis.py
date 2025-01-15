"""
Analysis module, containing the core logic for data analysis.
"""

import os
import re
import logging
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Side
from sklearn.metrics import r2_score
from sklearn.linear_model import LinearRegression

from utils import get_resource_path
from config import (DEFAULT_X_COLUMN, DEFAULT_Y_COLUMN, OUTPUT_IMAGE_DIR, DEFAULT_PRELOAD, DEFAULT_Yield_Force_Constant,
                    DEFAULT_Displacement_Constant, Excel_Type)


def analyse_data(csv_file, x_column=DEFAULT_X_COLUMN, y_column=DEFAULT_Y_COLUMN, min_window_size=10, max_window_size=20, preload=DEFAULT_PRELOAD,
                 YFC=None, dispc = None):
    """
    Performs linear regression analysis.

    Args:
        csv_file (str): The path to the CSV file.
        x_column (str, optional): The column name for the X-axis data. Defaults to `DEFAULT_X_COLUMN`.
        y_column (str, optional): The column name for the Y-axis data. Defaults to `DEFAULT_Y_COLUMN`.
        min_window_size (int, optional): The minimum size of the linear regression window. Defaults to 10.
        max_window_size (int, optional): The maximum size of the linear regression window. Defaults to 20.
        preload (float, optional): The preload value. Defaults to `DEFAULT_PRELOAD`.

     Returns:
        dict or None: A dictionary containing the analysis results and data for plotting, or None if an error occurs.
    """
    results = {}
    results_plot = {}

    try:
        df = pd.read_csv(csv_file)
        if x_column not in df.columns or y_column not in df.columns:
            raise ValueError(f"Column '{x_column}' or '{y_column}' not found in the CSV file.")

        force_col = df[y_column]
        max_index = force_col.idxmax()
        pre_index_series = force_col[:max_index][force_col[:max_index] <= 0]
        if pre_index_series.empty:
            pre_index = 0
        else:
            pre_index = pre_index_series.idxmax()
        first_index = force_col[force_col.index >= pre_index][force_col[force_col.index >= pre_index] >= preload].index.min()
        last_index = None
        for i in range(max_index + 1, len(force_col) - 1):
            if force_col[i] >= force_col[i - 1]:
                last_index = i-1
                break
        if last_index is None:
            last_index = df[df[y_column] >= preload].index.max()
        if first_index is not None:
            df = df.loc[first_index:last_index]
        else:
            df = pd.DataFrame(columns=df.columns)

        x_data = df[x_column].values
        y_data = df[y_column].values

        results_plot["x_data"] = x_data
        results_plot["y_data"] = y_data

        max_disp = df[x_column].max()

        max_value = df[y_column].max()
        results["Max Force"] = max_value

        best_r2 = -1
        best_model = None
        best_start = None
        best_end = None

        for current_window_size in range(min_window_size, max_window_size + 1):
            for i in range(0, len(x_data) - current_window_size + 1):
                x_window = x_data[i:i + current_window_size].reshape(-1, 1)
                y_window = y_data[i:i + current_window_size]

                model = LinearRegression()
                model.fit(x_window, y_window)
                y_pred = model.predict(x_window)

                r2 = r2_score(y_window, y_pred)

                if r2 > best_r2:
                    best_r2 = r2
                    best_model = model
                    best_start = i
                    best_end = i + current_window_size

        a = best_model.coef_[0]
        b = best_model.intercept_

        results_plot["a"] = a
        results_plot["b"] = b

        results["Stiffness"] = a

        results_plot["best_start"] = best_start
        results_plot["best_end"] = best_end

        next_x = None
        next_y = None

        if y_data[best_end - 1] == max_value:
            next_x = x_data[best_end - 1]
            next_y = y_data[best_end - 1]
        else:
            if best_end < len(x_data):
                for i in range(best_end, len(x_data)):
                    shifted_expected_y = YFC * a * (x_data[i] - max_disp*dispc) + b
                    if 0.8 * shifted_expected_y <= y_data[i] <= shifted_expected_y:
                        next_x = x_data[i]
                        next_y = y_data[i]
                        break
                    if i == len(x_data) - 1 and next_x is None:
                        next_x = x_data[best_end - 1]
                        next_y = y_data[best_end - 1]
        max_index = int(np.argmax(y_data))

        min_after_max_index = len(y_data) - 1
        min_after_max_value = float('inf')

        for i in range(max_index + 1, len(y_data)):
            if 0.5 <= y_data[i] < min_after_max_value:
                min_after_max_value = y_data[i]
                min_after_max_index = i

        results["Yield force"] = next_y
        results_plot["yield_force_x"] = next_x
        results_plot["yield_force_y"] = next_y
        postyield_displacement = x_data[min_after_max_index] - next_x
        results["Postyield Displacement"] = postyield_displacement

        auc = np.trapz(y_data[:min_after_max_index], x_data[:min_after_max_index])
        results["Work to fracture"] = auc

        output_result = [results["Max Force"], results["Stiffness"], results.get("Yield force", "N/A"),
                         results.get("Postyield Displacement", "N/A"), results["Work to fracture"]]

        return {"results": output_result, "results_plot": results_plot}

    except Exception as e:
        logging.error(f"Error in create_scatter_plot: {e}")
        return None


def create_scatter_plot(title="3point", xlabel=DEFAULT_X_COLUMN, ylabel=DEFAULT_Y_COLUMN, output_image="scatter_plot.png", results_plot=None):
    """
        Creates a scatter plot.

        Args:
            title (str, optional): The title of the plot. Defaults to "3point".
            xlabel (str, optional): The label for the X-axis. Defaults to `DEFAULT_X_COLUMN`.
            ylabel (str, optional): The label for the Y-axis. Defaults to `DEFAULT_Y_COLUMN`.
            output_image (str, optional): The filename for the output image. Defaults to "scatter_plot.png".

    """
    try:
        x_data = results_plot["x_data"]
        y_data = results_plot["y_data"]

        plt.figure(figsize=(8, 6))
        plt.scatter(x_data, y_data, label="other")
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.grid(True)

        best_start = results_plot["best_start"]
        best_end = results_plot["best_end"]

        a = results_plot['a']
        b = results_plot['b']

        x_fit_window = x_data[best_start:best_end]
        y_fit_window = y_data[best_start:best_end]

        plt.scatter(x_fit_window, y_fit_window, color='yellow', label="linear")
        x_fit_line = np.array([x_data.min(), x_data.max()])
        y_fit_line = a * x_fit_line + b
        plt.plot(x_fit_line, y_fit_line, color='red', label='linear line')

        plt.scatter(results_plot["yield_force_x"], results_plot["yield_force_y"], color='black', label="YF")
        plt.legend()
        plt.savefig(output_image)
        plt.close()

    except Exception as e:
        logging.error(f"Error in create_scatter_plot: {e}")
        plt.close()
        return None


def save_files(file_path, progress_callback, on_complete, min_window_size, max_window_size, failed_files_callback, preload=DEFAULT_PRELOAD,
               YFC=DEFAULT_Yield_Force_Constant, disp_c=DEFAULT_Displacement_Constant):
    """
    Analyzes all CSV files in a specified folder and writes the results to an Excel file.

    Args:
        file_path (str): The path to the folder containing the CSV files.
        progress_callback (function): A callback function to update progress.
        on_complete (function): A callback function to call upon completion.
        min_window_size (int): The minimum size of the linear regression window.
        max_window_size (int): The maximum size of the linear regression window.
        failed_files_callback (function): A callback function to update the list of failed files.
        preload (float, optional): The preload value. Defaults to `DEFAULT_PRELOAD`.
    """
    all_results = []
    png_dir = get_resource_path(file_path + OUTPUT_IMAGE_DIR)
    os.makedirs(png_dir, exist_ok=True)

    files = []
    failed_files = []

    for root, _, filenames in os.walk(file_path):
        for filename in filenames:
            if filename.endswith("Data.csv"):
                files.append(os.path.join(root, filename))

    total_files = len(files)

    for index, f in enumerate(files):
        try:
            file_name = os.path.basename(os.path.dirname(f))
            output_image = get_resource_path(os.path.join(png_dir, file_name + '.png'))
            analysis_output = analyse_data(f, x_column=DEFAULT_X_COLUMN, y_column=DEFAULT_Y_COLUMN, min_window_size=min_window_size,
                                           max_window_size=max_window_size, preload=preload, YFC=YFC, dispc=disp_c)
            result = analysis_output["results"]
            my_plot = analysis_output["results_plot"]
            create_scatter_plot(title=file_name, output_image=output_image, results_plot=my_plot)

            if result:
                all_results.append([file_name] + result)
            else:
                failed_files.append(os.path.basename(f))
        except Exception as e:
            logging.error(f"Error processing file {f}: {e}")
            failed_files.append(os.path.basename(f))
        progress_callback(index + 1, total_files)

    wb = Workbook()
    ws = wb.active
    headers = ["File Name", "Max Force", "Stiffness", "Yield force", "Postyield Displacement", "Work to fracture"]
    ws.append(headers)
    last_first_char = None
    for index, entry in enumerate(all_results):
        file_name = entry[0]
        match = re.match(r"([A-Za-z]+)", file_name)
        current_first_char = match.group(1) if match else ''
        if last_first_char is not None and current_first_char != last_first_char:
            ws.append([])
            ws.append([])
        ws.append(entry)
        last_first_char = current_first_char
        progress_callback(index + 1 + total_files, total_files * 2)

    ws.column_dimensions['A'].width = Excel_Type[0]
    ws.column_dimensions['B'].width = Excel_Type[1]
    ws.column_dimensions['C'].width = Excel_Type[2]
    ws.column_dimensions['D'].width = Excel_Type[3]
    ws.column_dimensions['E'].width = Excel_Type[4]
    ws.column_dimensions['F'].width = Excel_Type[5]

    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'),
                         top=Side(style='thin'), bottom=Side(style='thin'))

    for row in range(1, ws.max_row + 1):
        for col in range(1, ws.max_column + 1):
            cell = ws.cell(row=row, column=col)
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = thin_border

    for row in range(2, ws.max_row + 1):
        for col in range(2, ws.max_column + 1):
            cell = ws.cell(row=row, column=col)
            cell.number_format = '0.0000'
    try:
        excel_file_path = get_resource_path(file_path + ".xlsx")
        wb.save(excel_file_path)
        logging.info(f"Excel file saved to {excel_file_path}")
    except Exception as e:
        logging.error(f"Error saving excel file: {e}")

    failed_files_callback(failed_files)
    on_complete()
