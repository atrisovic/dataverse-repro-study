
# coding: utf-8

# # Get list of r-script DOIs in Harvard dataverse
# 
# Get list of dois for all R files in a dataverse (defaulting to Harvard's)
# Parameters
# ----------
# `dataverse_key` : string 
#                 containing user's dataverse API key
#                 
# `save` : boolean
#        whether or not to save the result as a .txt file
#        
# `print_status` : boolean
#                whether or not to print status messages
#                
# `api_url` : string
#           url pointing to the dataverse to get URLs for
#           
# Returns
# -------
# `r_dois` : list of string
#          dois containing r_files in Harvard dataverse

# In[49]:


from helpers import *


# In[50]:


# some constants
dataverse_key = "2a301287-c8e8-43f5-9862-cf084b310341"
api_url="https://dataverse.harvard.edu/api/search/"
max_retries=5

# defining some constants
r_file_query = "fileContentType:type/x-r-syntax"

# initialize variables to store current state of scraping
page_num = 0
r_dois = []
failures = 0
numfiles = 0

save=True
print_status=True


# ## keep requesting until the API returns fewer than 1000 results

# In[51]:


while True:
    if print_status:
            print("Requesting page {} from API...".format(page_num))
    try:
            #query the API for 1000 results
            myresults = requests.get(api_url,
                                     params= {"q": r_file_query, "type": "file",
                                              "key": dataverse_key, "start": str(1000 * page_num),
                                              "per_page": str(1000)}).json()['data']['items']
            if print_status:
                print("Parsing results from page {}...".format(page_num))
            
            # iterate through results, recording dataset_citations
            for myresult in myresults:
                # extract the DOI (if any) from the result
                doi_match = re.search("(doi:[^,]*)", myresult['dataset_persistent_id'])
                if doi_match:
                    r_dois.append(doi_match.group(1) + '\n')
    #retry if failed to pull data
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


# Note: in the original study the number of R files was 3407 and now it's 5100+

# In[52]:


import json
print(json.dumps(myresults[0:2], indent=4, sort_keys = True))


# In[53]:


myresults[1]['dataset_citation']


# In[54]:


for myresult in myresults:
    # extract the DOI (if any) from the result
    doi_match = re.search("(doi:[^,]*)", myresult['dataset_persistent_id'])
    # print doi_match
    if doi_match:
        r_dois.append(doi_match.group(1) + '\n')
        
print(r_dois[:3])  


# ## remove duplicate DOIs

# In[55]:


print(len(r_dois))
r_dois = list(set(r_dois))


# ## if save, then save as .txt file 

# In[56]:


if save:
    # remove old output file if one exists
    if os.path.exists('r_dois.txt'):   
        os.remove('r_dois.txt')

    # write dois to file, one-per-line
    with open('r_dois.txt', 'a') as myfile:
        for doi in r_dois:
            myfile.write(doi)


# In[57]:


r_dois[:5]


# In[58]:


len(r_dois)


# ## convert to directory names

# In[59]:


all_doi_dirs = [doi_to_directory(doi.strip()) for doi in r_dois]


# In[60]:


# There are 846 datasets containing a total of 3406 R scripts
len(r_dois)


# In[62]:


all_doi_dirs[:5]


# In[ ]:




