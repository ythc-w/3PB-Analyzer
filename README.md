# 3PB-Analyzer

This repository contains the source code for the 3PB-Analyzer, a Python application designed for analyzing three-point bending (3PB) test data. The application processes CSV files containing force-displacement data, performs linear regression analysis, and calculates key mechanical properties. It also provides visualizations and supports batch processing.



## Features

**Data Analysis:** Reads CSV files containing force-displacement data. 

**Linear Regression:** Performs linear regression to determine material stiffness.  

**Key Property Calculation:** Calculates Max Force, Stiffness, Yield Force, Post-yield Displacement, and Work to Fracture.  

**Data Visualization:** Generates scatter plots with linear regression fits and highlighted key points.   

**Batch Processing:** Processes multiple CSV files within a directory and outputs the analysis into a single Excel file, with plots for each CSV file. 

**Customizable Parameters:** Allows configuration of the linear regression window size, the preload value for data filtering, Yield Force Constant (YFC), and Displacement Constant (dispc). 

**Error Handling:** Includes robust error handling and logging to manage potential issues during file processing or analysis. 

 **User-Friendly GUI:** Utilizes a graphical user interface for ease of use.  

**Resource Management:**  Manages resource access consistently across different environments (development or packaged application).

**Clear Output:** Provides well-formatted Excel files and PNG plots for easy review of analysis results. 



## Installation

1. **Clone the repository:**

   ```git clone https://github.com/ythc-w/3PB-Analyzer    ```

   ```cd 3PB-Analyzer    ```

2. **Create a Virtual Environment (Recommended):**     

   It is highly recommended to create a virtual environment to isolate the project's dependencies:     

   ```python -m venv your_venv    ```

   ```source venv/bin/activate  ```

   ```# On Linux/macOS    ```

   ```# venv\Scripts\activate   On Windows    ```

3. **Install dependencies:**    

   ```pip install -r requirements.txt    ```



## Data File Instructions

This program requires data files to be organized according to a specific directory structure and naming convention. This is designed to match the structure of raw data files generated from three-point bending experiments. The data file directory structure **must strictly adhere** to the following requirements, otherwise, the program will not be able to locate the necessary data files.

**Data File Directory Structure:**

The program requires a root folder, such as `femur-3PBdata` in the example. This root folder **must** contain at least two subfolders, with each subfolder representing an experimental sample.  These subfolder names will be used to identify samples and determine the names of their corresponding CSV files. 

**Example File Directory Structure:**

femur-3PBdata/ 

├── A023/

------├── A023Data.csv

------└── … (other files or folders) 

└── A024/ 

------├── A024Data.csv 

------└── … (other files or folders)

└── … (other folders)

**Key Naming Conventions:**

1. **Root Folder Name:** You can choose any name for the root folder, such as `femur-3PBdata`. This folder will be the one you select when running the program. 
2. **Subfolder Names:** Data for each sample must be placed inside a subfolder named after the sample (e.g., `A023`, `A024`).  The folder name (e.g., `A023`) is a unique identifier used to name the data file. 
3. **CSV File Names:** Each sample subfolder must contain *one* CSV file. The CSV file's name **must** be in the format "**`subfolder name`+Data.csv**". For example, the CSV file in the `A023` folder *must* be named `A023Data.csv`. 

**More File Structure Examples:**  

If your sample name is `B101`, your directory structure should look like this:

femur-3PBdata/ 

├── B101/

------├── B101Data.csv 

------└── … (other files or folders) 

└── … (other folders)

**Important Notes:** 

*  **Number of Folders:** The root folder can contain multiple subfolders named after samples. The program will process all subfolders that match the naming conventions. 
* **CSV File Format:** The format of the data within the CSV files must be consistent with the format the program expects. Please refer to the program code for details on expected data formats. 
* **Additional Files:** You can include other files in the sample subfolders without interfering with the program's ability to find and read the CSV files. However, it's best practice to keep unnecessary files outside of these subfolders to maintain organizational clarity.  
* **Strict Adherence:** You **must strictly adhere** to the rules described above when organizing your file directory and naming files. Any deviation will prevent the program from properly identifying the data files and may lead to errors. 

**Running the Program:** 

1. Organize your data files into a folder as described above. 
2. Run the program and select the root folder containing all of your sample subfolders (e.g., `femur-3PBdata`).
3. The program will automatically identify and process the data files that match the specified naming conventions. 

Please ensure that your data file structure matches the requirements described here for the program to function correctly.



## Usage 

The application is primarily accessed through its graphical user interface (GUI). 

1. **Launch the Application:** Run the `gui.py` file:    

   ```python gui.py    ``` 

2. **Select Data Folder:**

   Use the "Select Original Folder" button to choose the directory containing the CSV data files for analysis. 

3. **Configure Analysis Parameters (Optional):** Adjust the following parameters if needed:        

   * **Window Size:**  Set the minimum and maximum sizes for the linear regression window.
   * **Yf_Constant:** Set the value of the Yield Force Constant (YFC).
   * **Preload:** Set the value of the preload force used to filter the raw data.

   * **Disp_Constant:** Set the value of the Displacement Constant (dispc).

4. **Run Analysis:** Click "Generate Excel And Png" to start the analysis. The progress bar will indicate the analysis's current status, and the application will provide visual feedback upon completion. 

5. **Output Files:**  The application will generate an Excel file with the processed data and plots. The name of the excel file is the same name as the directory containing the data with the extension ".xlsx", along with a PNG plot for each of the CSV files found in the directory. 

6.  **Error Handling:** The GUI will display a list of files that failed to process, which you can investigate. 

   

## File Structure

3PB-Analyzer/ 

├── 3PB-Analyzer/ 

------├── analysis.py   # Core analysis logic and functions 

------├── config.py   # Configuration parameters for the GUI and analysis 

------├── gui.py   # Main GUI module with tkinter 

------├── utils.py   # Utility functions for file handling 

├── femur-3PBdata/

------├── A023/

------------├── A023Data.csv

------└── A024/ 

------------├── A024Data.csv 

├── GUI/ 

------├── 3PB-Analyzer-GUI.exe 

------└── _internal/ 

------------└── …

├──.gitattributes

├──LICENSE

├── README.md  

├── requirements.txt   # List of required Python packages 



## Modules Overview

**'analysis.py':** Contains the core logic for data analysis. This module includes functions to read CSV files, perform linear regression, calculate material properties, and create scatter plots.  

**'config.py':** Manages the application's configuration settings, such as window dimensions, column names, regression window parameters, and output paths. This file allows for easy modification of these parameters. 

**'gui.py':** Implements the graphical user interface using `tkinter`. This module handles user interaction, directory selection, parameter input, and the display of progress and error messages. It utilizes a threaded approach to keep the interface responsive during analysis. 

**'utils.py':**  Provides utility functions, notably a function to get the absolute path of resources, which ensures the program functions correctly in both development and packaged environments. 



## Running the EXE File

Your executable (`3PB-Analyzer-GUI.exe`) is located within the `GUI` folder, along with an `_internal` folder.  ***\*These files must be in the same folder to run the program.\****  The functionality of the program will be identical to running the code in the development environment. 

**Instructions:**

1. **Copy the necessary files:** Copy the `3PB-Analyzer-GUI.exe` file and the `_internal` folder to a new folder. This new folder will be the working directory for the program.  Crucially, the `_internal` folder must be a **direct** subfolder of the folder containing `3PB-Analyzer-GUI.exe`.  Do **not** place the `_internal` folder in a separate location. 
2. **Run the executable:** Double-click the `3PB-Analyzer-GUI.exe` file to launch the program. The GUI should appear and function as expected. 

**Important Considerations:** 

* **Path Issues:** Files within the `_internal` folder (e.g., data files, images) are assumed to be relative to the `3PB-Analyzer-GUI.exe` file's location.  Therefore, these files must be in the correct folder for the program to work correctly.  Inconsistent or incorrect paths can lead to failure. 
* **Resource Files:** Ensure all necessary resource files (e.g., images, configuration files, other binary files) are correctly packaged within the `_internal` folder. 
* **Error Handling:** If you encounter any runtime errors (e.g., files not found), carefully review the file paths within the `_internal` folder to ensure they're valid and complete. 

**Example Usage:** 

If you want to run your program in the `C:\MyPrograms\` directory, copy the entire `GUI` folder (containing `3PB-Analyzer-GUI.exe` and `_internal`) into `C:\MyPrograms\`.  This is **critical** for correct operation. 

C:\MyPrograms
├── 3PB-Analyzer-GUI.exe

└── _internal/

└── … 

**Project Structure After Packaging:**

You need to copy the *entire* `GUI` folder, not just the `3PB-Analyzer-GUI.exe` file, into the desired working directory.  This is a fundamental requirement for the packaged application to run correctly. 

GUI/ 

├── 3PB-Analyzer-GUI.exe

└── _internal/ 

└── …

**Common Pitfalls and How to Avoid Them:** 

* **Path Errors:** Ensure that file paths used by your Python code (especially when reading data) are correct and properly relative to the `_internal` folder. Incorrect or missing paths will almost certainly cause the program to fail. 
* **Necessary Files:** Confirm that the `_internal` folder contains all necessary data files and resources. 
* **Permissions:** Ensure the user running the program has read permissions for all files within the `_internal` folder.  

By understanding and addressing these points, you will significantly improve the reliability of your packaged application. Remember to verify all file paths and folder structure.
