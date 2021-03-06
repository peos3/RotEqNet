# Global imports
import os

# Local imports
from parser import Parser

data_folder = "./data/"
combined_folder = "combined"
if not os.path.isdir(data_folder):
    data_folder = "." + data_folder

p = Parser(data_folder, combined_folder)

for sub_folder in os.listdir(data_folder):
    sub_path = os.path.join(data_folder, sub_folder)
    if os.path.isdir(sub_path):
        p.create_cropped_files(sub_folder, (300, 400), overwrite=True)

# p.combine_numpy_arrays()
print("Finished.")
