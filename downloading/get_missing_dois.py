
# coding: utf-8

# In[1]:


from helpers import *


# In[2]:


# some constants
dataverse_key = "3b0777ab-4af9-4b3a-971e-5c84ac75926b"


# # get list of r-script DOIs in Harvard dataverse

# In[3]:


all_dois = get_r_dois(dataverse_key, save=True, print_status=True)


# In[15]:


all_dois[:5]


# In[16]:


# write all dois
with open("all_dois_02_28_18.txt", 'w') as handle:
    map(lambda doi: handle.write(doi + "\n"), all_dois)


# In[18]:


all_dois = []
with open("r_dois.txt", 'r') as handle:
    all_dois = [doi.strip() for doi in handle.readlines()]
    
all_dois


# In[7]:


#if not os.path.exists("../RDatasets"):
#    os.makedirs("../RDatasets")


# In[19]:


# get list of r-script dois currently downloaded in the last download operation
downloaded = [directory_to_doi(doi) for doi in os.listdir("../RDatasets")]


# In[9]:


missing_dois = list(set(all_dois) - set(downloaded))


# In[10]:


# write missing dois to file
with open("missing_dois.txt", 'w') as handle:
    map(lambda doi: handle.write(doi + "\n"), missing_dois)


# In[12]:


# create new file to store the directory names
with open("downloaded_dois.txt", 'w') as handle:
    map(lambda doi: handle.write(doi + "\n"), os.listdir("../RDatasets"))


# In[ ]:




