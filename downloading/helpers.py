import requests
import json
import re
import os
import sys
import shutil
import fnmatch
import pickle
import codecs
import chardet

import pandas as pd
import numpy as np


def doi_to_directory(doi):
	"""Converts a doi string to a more directory-friendly name
	Parameters
	----------
	doi : string
		  doi
	
	Returns
	-------
	doi : string
		  doi with "/" and ":" replaced by "-" and "--" respectively
	"""
	return doi.replace("/", "-").replace(":", "--")

def directory_to_doi(doi):
	"""Converts a doi string to a more directory-friendly name
	Parameters
	----------
	doi : string
		  doi
	
	Returns
	-------
	doi : string
		  doi with "-" and "--" replaced by "/" and ":" respectively
	"""
	return doi.replace("--", ":").replace("-", "/")

def get_r_dois(dataverse_key, save=False, print_status=False,
			   api_url="https://dataverse.harvard.edu/api/search/", max_retries=5):
	"""Get list of dois for all R files in a dataverse (defaulting to Harvard's)
	Parameters
	----------
	dataverse_key : string 
					containing user's dataverse API key
	save : boolean
		   whether or not to save the result as a .txt file
	print_status : boolean
				   whether or not to print status messages
	api_url : string
			  url pointing to the dataverse to get URLs for
	Returns
	-------
	r_dois : list of string
			 dois containing r_files in Harvard dataverse
	"""
	# defining some constants
	r_file_query = "fileContentType:type/x-r-syntax"

	# initialize variables to store current state of scraping
	page_num = 0
	r_dois = []
	failures = 0
	numfiles = 0

	#  keep requesting until the API returns fewer than 1000 results
	while True:
		if print_status:
			print("Requesting page {} from API...".format(page_num))
		try:
			# query the API for 1000 results
			myresults = requests.get(api_url,
									 params= {"q": r_file_query, "type": "file",
									 "key": dataverse_key,
									 "start": str(1000 * page_num),
									 "per_page": str(1000)}).json()['data']['items']

			if print_status:
				print("Parsing results from page {}...".format(page_num))
			
			# iterate through results, recording dataset_citations
			for myresult in myresults:
				# extract the DOI (if any) from the result
				doi_match = re.search("(doi:[^,]*)", myresult['dataset_citation'])
				if doi_match:
					r_dois.append(doi_match.group(1) + '\n')
		# retry if failed to pull data
		except:
			if print_status:
				print("Failed to fetch results for page {}. {} retries left".format(page_num,
																					max_retries - 1 - failures))
			if failures < max_retries:
				failures += 1
				continue
			else:
				break

		# if fewer than 1000 results were returned; we must have reached the end
		if len(myresults) < 1000:
			if print_status:
				print("Reached last page of results. Done.")
				print("Total Number of R Files: {}".format(numfiles + len(myresults)))
			break
		page_num += 1
		numfiles += 1000

	# remove duplicate DOIs
	r_dois = list(set(r_dois))

	# if save, then save as .txt file 
	if save:
		# remove old output file if one exists
		if os.path.exists('r_dois.txt'):   
			os.remove('r_dois.txt')

		# write dois to file, one-per-line
		with open('r_dois.txt', 'a') as myfile:
			for doi in r_dois:
				myfile.write(doi)
	return r_dois

def download_dataset(doi, destination, dataverse_key,
					 api_url="https://dataverse.harvard.edu/api/search/"):
	"""Download doi to the destination directory
	Parameters
	----------
	doi : string
		  doi of the dataset to be downloaded
	destination : string
				  path to the destination in which to store the downloaded directory
	dataverse_key : string
					dataverse api key to use for completing the download
	api_url : string
			  URL of the dataverse API to download the dataset from
	Returns
	-------
	bool
	whether the dataset was successfully downloaded to the destination
	"""

	# make a new directory to store the dataset
	# (if one doesn't exist)
	if not os.path.exists(destination):   
		os.makedirs(destination)

	try:
		# query the dataverse API for all the files in a dataverse
		files = requests.get("https://dataverse.harvard.edu/api/datasets/:persistentId",
							 params= {"persistentId": doi, "key": dataverse_key})\
							 .json()['data']['latestVersion']['files']
	except:
		return False

	# convert DOI into a friendly directory name by replacing slashes and colons
	doi_direct = destination + '/' + doi.replace("/", "-").replace(":", "--")

	# make a new directory to store the dataset
	if not os.path.exists(doi_direct):   
		os.makedirs(doi_direct)

	# for each file result
	for file in files:
		try:
			# parse the filename and fileid 
			filename = file['dataFile']['filename']
			fileid = file['dataFile']['id']

			# query the API for the file contents
			response = requests.get("https://dataverse.harvard.edu/api/access/datafile/" + str(fileid),
									params={"key": dataverse_key})

			# write the response to correctly-named file in the dataset directory
			with open(doi_direct + "/" + filename, 'w') as handle:
				handle.write(response.content)
		except:
			return False

	return True

def get_runlog_data(path_to_datasets):
	"""Aggregate run-time data for all datasets in the given
	Parameters
	----------
	path_to_datasets : string 
					   path to the directory containing processed datasets
	Returns
	-------
	(run_data_df, error_dois) : tuple of (pandas.DataFrame, list of string)
								a tuple containing a pandas DataFrame with the 
								aggregated results of attempting to run the R code
								in all the datasets, followed by a list of datasets
								for which aggregating the results failed (should be
								an empty list unless there was a catastrophic error)
	
	"""
	# get list of dataset directories, ignoring macOS directory metadata file (if present)
	doi_directs = [doi for doi in os.listdir(path_to_datasets) if doi != '.DS_Store']
	# initialize empty dataframe to store run logs of all the files
	run_data_df = pd.DataFrame()
	# initialize empty list to store problem doi's
	error_dois = []

	# iterate through directories and concatenate run logs
	for my_doi in doi_directs:
		try:
			# assemble path
			my_path = path_to_datasets + '/' + my_doi + '/prov_data/' + 'run_log.csv'
			# concatenate to dataframe
			run_data_df = pd.concat([run_data_df, pd.read_csv(my_path)])
		except:
			error_dois.append(my_doi)
	return (run_data_df, error_dois)

def get_missing_files(path_to_datasets, pickle_path):
	"""Aggregate missing files data for all datasets in the given path and pickle the result
	Parameters
	----------
	path_to_datasets : string 
					   path to the directory containing processed datasets
	pickle_path : string
				  path to pickle file to store the dictionary
	"""
	# get list of dataset directories, ignoring macOS directory metadata file (if present)
	doi_directs = [doi for doi in os.listdir(path_to_datasets) if doi != '.DS_Store']
	missing_dict = {}

	# iterate through directories and concatenate run logs
	for my_doi in doi_directs:
		if my_doi.startswith("doi"):
			missing_dict[my_doi] = []
			try:
				# assemble path
				my_path = path_to_datasets + '/' + my_doi + '/prov_data/' + 'missing_files.txt'
				# open the file for reading and collect the results
				with open(my_path, 'r') as my_file:
					for line in my_file.readlines():
						if line.strip():
							missing_dict[my_doi].append(line.strip())
					missing_dict[my_doi] = list(set(missing_dict[my_doi]))
			except:
				pass

	# pickle the file
	with open(pickle_path + '/missing_files.pkl', 'wb') as handle:
		pickle.dump(missing_dict, handle, protocol=pickle.HIGHEST_PROTOCOL)

def refresh_datasets(path_to_datasets, path_to_archive):
	"""Clean datasets of all traces of preprocessing and provenance collection
	Parameters
	----------
	path_to_datasets : string 
					   path to the directory containing processed datasets
	path_to_archive : string
					  path to the directory to move preprocessed files to
	"""
	# get list of dataset directories, ignoring macOS directory metadata file (if present)
	doi_directs = [doi for doi in os.listdir(path_to_datasets) if doi != '.DS_Store']

	# create a new archive directory, deleting any directories with the same path and name
	if os.path.exists(path_to_archive):
		shutil.rmtree(path_to_archive)
	os.makedirs(path_to_archive)

	# iterate through directories, deleting prov_data directory and preprocessed files
	for my_doi in doi_directs:
		# assemble paths
		doi_dir_path = path_to_datasets + '/' + my_doi
		# get list of ignoring macOS directory metadata file (if present)
		doi_files = [my_file for my_file in os.listdir(doi_dir_path) if\
					 my_file != '.DS_Store' and re.match('.*__preproc__', my_file)]

		# create a new doi archive directory, deleting any directories with the same path and name
		if os.path.exists(path_to_archive + "/" + my_doi):
			shutil.rmtree(path_to_archive + "/" + my_doi)
		os.makedirs(path_to_archive + "/" + my_doi)

		# remove preprocessed files
		for my_file in doi_files:
			doi_file_path = doi_dir_path + '/' + my_file
			try:
				shutil.move(doi_file_path, '/'.join([path_to_archive, my_doi, my_file]))
			except OSError:
				pass
		# remove prov_data directory
		try:
			shutil.rmtree(doi_dir_path + '/prov_data')
		except:
			pass

def find_file(pattern, path):
	"""Recursively search the directory pointed to by path for a file matching pattern.
	   Inspired by https://stackoverflow.com/questions/120656/directory-listing-in-python
	Parameters
	----------
	pattern : string
			  unix-style pattern to attempt to match to a file
	path : string
		   path to the directory to search

	Returns 
	-------
	string 
	path to a matching file or the empty string
	"""
	len_root_path = len(path.split('/'))
	for root, dirs, files in os.walk(path):
		for name in files:
			if fnmatch.fnmatch(name, pattern):
				return '/'.join((os.path.join(root, name)).split('/')[len_root_path:])
	return ''

def find_dir(pattern, path):
	"""Recursively search the directory pointed to by path for a directory matching pattern.
	   Inspired by https://stackoverflow.com/questions/120656/directory-listing-in-python
	Parameters
	----------
	pattern : string
			  unix-style pattern to attempt to match to a directory
	path : string
		   path to the directory to search

	Returns 
	-------
	string 
	path to a matching directory or the empty string
	"""
	len_root_path = len(path.split('/'))
	for root, dirs, files in os.walk(path):
		for name in dirs:
			if fnmatch.fnmatch(name, pattern):
				return '/'.join((os.path.join(root, name)).split('/')[len_root_path:])
	return ''

def get_r_filename(r_file):
	"""Remove the file extension from an r_file using regex. Probably unnecessary 
	   but improves readability
	Parameters
	----------
	r_file : string
			 name of R file including file extension
	Returns
	-------
	string
	name of R file without file extension
	"""
	return re.split('\.[rR]$', r_file)[0]

def extract_filename(path):
	"""Parse out the file name from a file path
	Parameters
	----------
	path : string
		   input path to parse filename from
	Returns
	-------
	file_name : string
				file name (last part of path), 
				empty string if none found
	"""
	# get last group of a path
	if path:
		file_name = os.path.basename(path)
		file_name = re.match(".*?\s*(\S+\.[^ \s,]+)\s*", file_name)
		if file_name:
			return file_name.group(1)
	return ''

def find_rel_path(path, root_dir, is_dir=False):
	"""Attempt to search along a user-provided absolute path for 
	   the provided file or directory
	Parameters
	----------
	path : string 
		   input path to search for
	root_dir : string
			   root directory to begin search from
	is_dir : bool
			 whether the path is to a directory
	Returns
	-------
	rel_path : string
			   relative path to the directory or file or empty string
			   if not found
	"""
	path_dirs = path.split('/')
	item_name = path_dirs[-1]
	test_fun = os.path.isdir if is_dir else os.path.exists
	if test_fun(root_dir + '/' + item_name):
		return item_name
	else:
		# if path doesn't contain intermediate dirs, give up
		if len(path_dirs) == 1:
			return ''
		intermediate_dirs = reversed(path_dirs[:-1])
		try_path = item_name
		# iterate through intermediate path directories,
		# attempting to find the path
		for my_dir in intermediate_dirs:
			try_path = my_dir + '/' + try_path
			if test_fun(root_dir + '/' + try_path):
				return try_path
		return ''

def maybe_import_operation(r_command):
	"""Searches an r command for common import functions
	Parameters
	----------
	r_command : string
				command from R file
	Returns
	-------
	bool
	"""
	r_import_list = ['read', 'load', 'fromJSON', 'import', 'scan']
	for pattern in r_import_list:
		if re.search(pattern, r_command):
			return True
	return False

def preprocess_setwd(r_file, script_dir, from_preproc=False):
	"""Attempt to correct setwd errors by finding the correct directory or deleting the function call
	Parameters
	----------
	r_file: string
			name of the R file to be preprocessed
	script_dir : string
				 path to the directory containing the R file
	from_preproc : boolean
				   whether the r_file has already been preprocessed (default False)

	"""
	# parse out filename and construct file path
	filename = get_r_filename(r_file)
	file_path = script_dir + '/' + r_file
	# path to preprocessed file, named with suffix "_preproc"
	preproc_path = script_dir + '/' + filename + '__preproc__' + '.R'
	# path to temp file, named with suffix "_temp"
	file_to_copy = script_dir + '/' + filename + '_temp' + '.R'
	# if file has already been preprocessed, rename the preprocessed file
	# to a temporary file with _temp suffix, freeing up the __preproc__ suffix to be used 
	# for the file generated by this function
	if from_preproc:
		os.rename(preproc_path, file_to_copy)
	else:
		file_to_copy = file_path

	# for storing return value
	curr_wd = script_dir

	# wipe the preprocessed file and open it for writing
	with open(preproc_path, 'w') as outfile:
		# write code from .R file, replacing function calls as necessary
		with open(file_to_copy, 'r') as infile:
			for line in infile.readlines():
				# ignore commented lines
				if re.match("^#", line):
					outfile.write(line)
				else:
					contains_setwd = re.match("\s*setwd\s*\(\"?([^\"]*)\"?\)", line)
					# if the line contains a call to setwd
					if contains_setwd:
						# try to find the path to the working directory (if any)
						path_to_wd = find_rel_path(contains_setwd.group(1), curr_wd, is_dir=True)
						if not path_to_wd:
							path_to_wd = find_dir(os.path.basename(contains_setwd.group(1)),
												  curr_wd)
						# if a path was found, append modified setwd call to file
						if path_to_wd and path_to_wd != curr_wd:
							curr_wd += '/' + path_to_wd
							outfile.write("setwd(" + "\"" + path_to_wd + "\"" + ")\n")
					else:
						outfile.write(line)
	
	# remove the file with _temp suffix if file was previously preprocessed
	if from_preproc:
		os.remove(file_to_copy)

def preprocess_lib(r_file, path, from_preproc=False):
	"""Replace calls to "library", "require", and "install.packages" with a special function,
	   "install_and_load". Please see install_and_load.R for more details. 
	Parameters
	----------
	r_file: string
			name of the R file to be preprocessed
	file_path : string
				path to the directory containing the R file
	from_preproc : boolean
				   whether the r_file has already been preprocessed

	"""
	# parse out filename and construct file path
	filename = get_r_filename(r_file)
	file_path = path + "/" + r_file
	# path to preprocessed file, named with suffix "__preproc__"
	preproc_path = path + "/" + filename + "__preproc__" + ".R"
	# path to temp file, named with suffix "_temp"
	file_to_copy = path + "/" + filename + "_temp" + ".R"
	# if file has already been preprocessed, rename the preprocessed file
	# to a temporary file with _temp suffix, freeing up the __preproc__ suffix to be used 
	# for the file generated by this function
	if from_preproc:
		try:
			os.rename(preproc_path, file_to_copy)
		except:
			file_to_copy = file_path
	else:
		file_to_copy = file_path

	# wipe the preprocessed file and open it for writing
	with open(preproc_path, 'w') as outfile:
		# add in declaration for "install_and_load" at the head of the preprocessed file
		with open("install_and_load.R", 'r') as install_and_load:
			for line in install_and_load.readlines():
				outfile.write(line)
			outfile.write("\n")
		# write code from .R file, replacing function calls as necessary
		with open(file_to_copy, 'r') as infile:
			for line in infile.readlines():
				# ignore commented lines
				if re.match("^#", line):
					outfile.write(line)
				else:
					# replace "library" calls
					library_replace = re.sub("library\s*\(\"?([^\"]*)\"?\)",
											 "install_and_load(\"\\1\")", line)
					# replace "require" calls
					require_replace = re.sub("require\s*\(\"?([^\"]*)\"?\)",
											 "install_and_load(\"\\1\")", library_replace)
					# replace "install.packages" calls
					install_replace = re.sub("install.packages\s*\(\"?([^\"]*)\"?\)",
											 "install_and_load(\"\\1\")", require_replace)
					# write the preprocessed result
					outfile.write(install_replace)
					# if the line clears the environment, re-declare "install_and_load" immediately after
					if re.match("^\s*rm\s*\(", line):
						with open("install_and_load.R", 'r') as install_and_load:
							for line in install_and_load.readlines():
								outfile.write(line)
							outfile.write("\n")
	
	# remove the file with _temp suffix if file was previously preprocessed
	if from_preproc:
		try:
			os.remove(file_to_copy)
		except:
			pass

def preprocess_file_paths(r_file, script_dir, from_preproc=False, report_missing=False):
	"""Attempt to correct filepath errors 
	Parameters
	----------
	r_file: string
			name of the R file to be preprocessed
	script_dir : string
				 path to the directory containing the R file
	wd_path : string
			  path to the working directory the R file references, (root directory for file searches)
	from_preproc : bool
				   whether the r_file has already been preprocessed (default False)
	report_missing : bool
					 report when a file can't be found
	"""
	# parse out filename and construct file path
	filename = get_r_filename(r_file)
	file_path = script_dir + "/" + r_file
	# path to preprocessed file, named with suffix "_preproc"
	preproc_path = script_dir + "/" + filename + "__preproc__" + ".R"
	# path to temp file, named with suffix "_temp"
	file_to_copy = script_dir + "/" + filename + "_temp" + ".R"
	# path to write missing files to
	report_path = script_dir + "/prov_data/missing_files.txt" 
	# if file has already been preprocessed, create _temp file to copy from
	if from_preproc:
		try:
			os.rename(preproc_path, file_to_copy)
		except:
			file_to_copy = file_path
	else:
		file_to_copy = file_path

	curr_wd = script_dir

	# wipe the preprocessed file and open it for writing
	with open(preproc_path, 'w') as outfile:
		# write code from .R file, replacing function calls as necessary
		with open(file_to_copy, 'r') as infile:
			for line in infile.readlines():
				# if not a commented line
				if not re.match('^#', line):
					contains_setwd = re.match("\s*setwd\s*\(\"?([^\"]+)\"?\)", line)
					# track calls to setwd to look in the right place for files
					if contains_setwd:
						curr_wd += '/' + contains_setwd.group(1)
					potential_path = re.search('\((?:.*?file\s*=\s*|\s*)[\"\']([^\"]+\.\w+)[\"\']', line)
					if potential_path:
						# replace windows pathing with POSIX style
						line = re.sub(re.escape('\\\\'), '/', line)
						if maybe_import_operation(line):
							potential_path = potential_path.group(1)
							if potential_path:
								rel_path = find_rel_path(potential_path, curr_wd)
								if not rel_path:
									# try to find the path to the working directory (if any)
									rel_path = find_file(extract_filename(potential_path), curr_wd)
								# if a path was found, change the file part of the line
								if rel_path:
									line = re.sub(potential_path, rel_path, line)
								# if the path wasn't found, report file as missing
								elif report_missing:
									if not os.path.exists(script_dir + "/prov_data"):
										os.makedirs(script_dir + "/prov_data")
									with open(report_path, 'a+') as missing_out:
										missing_out.write(r_file + ',' + potential_path + '\n')
				outfile.write(line)
	
	# remove the file with _temp suffix if file was previously preprocessed
	if from_preproc:
		try:
			os.remove(file_to_copy)
		except:
			pass

def preprocess_source(r_file, script_dir, from_preproc=False):
	"""Correct filenames of sourced files
	Parameters
	----------
	r_file : string
			 name of the R file to be preprocessed
	script_dir : string
				  path to the directory containing the R file
	from_preproc : boolean
				   whether the r_file has already been preprocessed (default False)
	"""
	# parse out filename and construct file path
	preprocess_setwd(r_file, script_dir)
	filename = get_r_filename(r_file)
	file_path = script_dir + "/" + r_file
	# path to preprocessed file, named with suffix "_preproc"
	preproc_path = script_dir + "/" + filename + "__preproc__" + ".R"
	# path to temp file, named with suffix "_temp"
	file_to_copy = script_dir + "/" + filename + "_temp" + ".R"
	# if file has already been preprocessed, create _temp file to copy from
	if from_preproc:
		os.rename(preproc_path, file_to_copy)
	else:
		file_to_copy = file_path
	curr_wd = script_dir

	# wipe the preprocessed file and open it for writing
	with open(preproc_path, 'w') as outfile:
		# write code from .R file, replacing function calls as necessary
		with open(file_to_copy, 'r') as infile:
			for line in infile.readlines():
				# if not a commented line
				if not re.match('^#', line):
					contains_setwd = re.match("\s*setwd\s*\(\"?([^\"]*)\"?\)", line)
					# if the line contains a call to setwd
					if contains_setwd:
						curr_wd += '/' + contains_setwd.group(1)
					sourced_file = re.match('^\s*source\s*\((?:.*?file\s*=\s*|\s*)[\"\']([^\"]+\.[Rr])[\"\']', line)
					if sourced_file:
						sourced_file = sourced_file.group(1)
						# replace windows pathing with POSIX style
						line = re.sub(re.escape('\\\\'), '/', line)
						# try to fine the relative path
						rel_path = find_rel_path(sourced_file, curr_wd)
						if not rel_path:
							rel_path = find_file(extract_filename(sourced_file), curr_wd)
						# if relative path found, recursively call function on the sourced file
						if rel_path:
							sourced_filename = get_r_filename(os.path.basename(rel_path))
							outfile.write('source(' + '/'.join(rel_path.split('/')[:-1]) +\
										   '\"'+ sourced_filename + '__preproc__.R\")\n')
					else:
						outfile.write(line)
				else:
					outfile.write(line)
	
	# remove the file with _temp suffix if file was previously preprocessed
	if from_preproc:
		try:
			os.remove(file_to_copy)
		except:
			pass

def all_preproc(r_file, path, error_string="error"):
	"""Attempt to correct setwd, file path, and library errors
	Parameters
	----------
	r_file: string
			name of the R file to be preprocessed
	path : string
		   path to the directory containing the R file
	error_string : string
				   original error obtained by running the R script, defaults to
				   "error", which will perform the preprocessing
	"""
	# parse out filename and construct file path
	filename = get_r_filename(r_file)
	file_path = path + "/" + r_file
	# path to preprocessed file, named with suffix "_preproc"
	preproc_path = path + "/" + filename + "__preproc__" + ".R"
	# try all 3 preprocessing methods if there is an error
	if error_string != "success":
		preprocess_source(r_file, path, from_preproc=True)
		preprocess_lib(r_file, path, from_preproc=True)
		preprocess_file_paths(r_file, path, from_preproc=True, report_missing=True)
	# else just copy and rename the file
	else:
		shutil.copyfile(file_path, preproc_path)

def get_io_from_prov_json(prov_json):
	"""Identify input and output files from provenance JSON
	Parameters
	----------
	prov_json : OrderedDict
				ordered dictionary generated from json prov file using python's json module
				i.e. json.load(path_to_json_file, object_pairs_hook=OrderedDict)
				
	Returns
	-------
	(input_files, output_files, file_locs) : tuple of (list, list, dict)
											 input files and output files (empty lists if none) and 
											 dict mapping files to location (empty if none)
	"""
	# initializing data structures
	entity_to_file = {}
	file_locs = {}
	input_files = []
	output_files = []
	
	# get file entity names and locations
	for key, value in prov_json['entity'].items():
		if value['rdt:type'] == 'File':
			filename = value['rdt:name']
			entity_to_file[key] = filename
			file_locs[filename] = value['rdt:location']
	
	entities = set(entity_to_file.keys())
	
	# if a file entity is used by an activity, it must be an input file
	for value in prov_json['used'].values():
		if value['prov:entity'] in entities:
			input_files.append(entity_to_file[value['prov:entity']])
			
	# if a file entity was generated by an activity, it must be an output file
	for value in prov_json['wasGeneratedBy'].values():
		if value['prov:entity'] in entities:
			output_files.append(entity_to_file[value['prov:entity']])

	return input_files, output_files, file_locs

def get_pkgs_from_prov_json(prov_json):
	"""Identify packages used from provenance JSON
	Parameters
	----------
	prov_json : OrderedDict
				ordered dictionary generated from json prov file using python's json module
				i.e. json.load(path_to_json_file, object_pairs_hook=OrderedDict)
				
	Returns
	-------
	packages : list of tuple of (string, string)
			   list of (package_name, version) tuples
	"""
	# regular expression to capture library name
	library_regex = re.compile(r"library\((?P<lib_name>.*)\)", re.VERBOSE)

	# set of used libraries
	used_packages = set()

	# Identify libraries being used in script and add them to set
	for command in prov_json['activity'].values():
		code_line = command['rdt:name']
		# extract the package name from the JSON
		package_match = re.match('^\s*library\s*\((?:.*?package\s*=\s*|\s*)[\"\']([^\"]+)[\"\']', 
								 code_line)
		if not package_match:
			package_match = re.match('^\s*require\s*\((?:.*?package\s*=\s*|\s*)[\"\']([^\"]+)[\"\']',
									 code_line)
		# if a package name was found, add to the set
		if package_match:
			used_packages.add(package_match.group(1))
	
	# filter out pre-installed packages
	used_packages -= set(['datasets', 'utils', 'graphics', 'grDevices', 
						  'methods', 'stats', 'provR', 'devtools'])
	
	# list of (package, version) tuples
	packages = []
	
	# Filter packages in user's environment by which ones were used
	for package_dict in prov_json['activity']["environment"]["rdt:installedPackages"]:
		if package_dict["package"] in used_packages:
			packages.append((package_dict["package"], package_dict["version"]))
	
	return packages

"""
The following block of file decoding functions are heavily-modified versions of 
Sebastian RoccoSerra's answer on this Stack Overflow post:
https://stackoverflow.com/questions/191359/how-to-convert-a-file-to-utf-8-in-python
(block ends with a series of # marks)
"""
def get_encoding_type(current_file):
	detectee = open(current_file, 'rb').read()
	result = chardet.detect(detectee)
	return result['encoding']

def writeConversion(sourceFh, sourceFile, outputDir, targetFormat):
	if not os.path.exists(outputDir):
		os.makedirs(outputDir)
	with codecs.open(outputDir + '/' + sourceFile, 'w', targetFormat) as targetFile:
		for line in sourceFh:
			targetFile.write(line)

def convertFileWithDetection(sourceDir, sourceFile, outputDir, targetFormat, replace=False,
							 logs=False):
	if logs:
		print("Converting '" + sourceFile + "'...")
	sourcePath = os.path.join(sourceDir, sourceFile)
	if replace:
		os.rename(os.path.join(sourceDir, sourceFile),
				  os.path.join(sourceDir, "__orig__" + sourceFile))
		sourcePath = os.path.join(sourceDir,  "__orig__" + sourceFile)

	sourceFormat = get_encoding_type(sourcePath)
	
	try:
		with codecs.open(sourcePath, 'rU', sourceFormat) as sourceFh:
			writeConversion(sourceFh, sourceFile, outputDir, targetFormat)
			if logs:
				print('Done.')
		if replace:
			os.remove(sourcePath)
		return
	except UnicodeDecodeError:
		pass

	print("Error: failed to convert " + sourceFile + ".")

def convertFileBestGuess(filename):
	sourceFormats = ['ascii', 'iso-8859-1']
	for format in sourceFormats:
		try:
			with codecs.open(sourceFile, 'rU', format) as sourceFile:
				writeConversion(sourceFile)
				print('Done.')
				return
		except UnicodeDecodeError:
			pass
"""
End of file decoding function block from Stack Overflow
"""
def convert_r_files(path, replace=False, output_path=''):
	"""Convert all R files to utf-8 in the directory pointed to by path
	Parameters
	----------
	path : string
		   path to the directory containing R scripts
	output_path : string 
				  relative path from "path" parameter to directory
				  to place converted files
	replace : bool
			  whether to replace original files with converted ones
	"""
	targetFormat = 'utf-8'
	# calculate correct output 
	output_path = 'converted' if not output_path else output_path
	outputDir = path if replace else os.path.join(path, output_path)
	orig_files = [my_file for my_file in os.listdir(path) if\
				  my_file.endswith(".R") or my_file.endswith(".r")]
	for my_file in orig_files:
		convertFileWithDetection(path, my_file, outputDir, 'utf-8', replace)
