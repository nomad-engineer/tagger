# App Functions

## Intro

This app to aid the manual tagging of images for generation of stable diffusion loras or other machine learning programs that require tagged images. Other programs typicaly place image tags in a same named .txt caption file which is read by the training algorithum however this can be difficult to work with when exploring different tagging conventions or trying to manage very large libaries of images. To bypass this this app instead stores an images tags as a same named .json with tags orginised into categories to help filtering as well as other meta data that is usful to be kept with the image. 

### image.json

Contents of the image.json file:

```json
{
    "name": "image1",
    "caption": "a landscape",
    "tags": [
        {
            "category": "setting",
            "value": "mountain",
        },
        {
            "category": "camera",
            "value": "from front",
        },
        
    ]
}
```

The tags are stored as a list of dictionaries with the order of the list depicting the importance ordering of the tags. Every tag has a category and tag value.

When images are added to a project the relative path to the image is stored in the project file and a .json is created if it does not already exisit. The user then uses the apps tools to add lables to the images .json.

When then creating the .txt caption files the user has the option to set an export template to define which tags and in what order the tags are exported. This allows the user to create multiul projects with different tagging conventions without duplicating image and .txt file pairs or removing tags that are still relavent to the images for other tagging conventions or helpful for filtering.

### project.json

Each project saves its data in a project.json and follows the following format:

```json
{
    "project_name": "project 1",
    "description": "landscape style",
    "images": [
        {
            "path": rel/path/to/image.png
        },
    ],
    "export":{
        
    },
    "filters": {
        
    }
    "preferences":{
        
    },
}
```

**Images:** Lists a dict for each image in the project with an entry for its relative path from the project.json. It will also contain other project specifc data for the image

**Export:** Project specific data related to the export window

**Filters:** Project specific data related to the the filters window

**Preferences:** Project specific overrides for global preferences. 

# global.json

File created at the apps install directory that contains globaly applied settings. structure mimics that of the project.json. if a value is not specificed in the project.json then the value from the global.json is used.

## Project Creation

### Create New Project

To start a new project select new project from the file menu. This will open a dialoug set the save location for the project file. The location of the project file also serves as the root dir from which images file paths will be relative to. 

### Import Images

From the file/import images menu select the image files or folders from which to import images from. Images are imported recurcivly. When selected a dialog will appear which will give the user options on how to process the selected images including:

- 'Add tag to images'. By default this will be category: 'meta', tag value: 'imported: {timestamp}' with the timestamp been the same for all the images. This can be changed to any string by the user. This is typicaly used to make it easy for the user to filter the new images for tagging.

- 'Select images after import'. Tickbox that removes any images from the current selection and adds just the imported images to the selection.

When importing the importer does the following:

- Renames the image files to a hash value of the image. This is to ensure the name is unique. The lenght of the hash value is set in the global preferences or overwridden in the project specific preferences

- Creates the .json if it doesnt already exist and adds the image filename to the 'name' field.

- Adds the import tag to the images json if one is provided

- If 'Select images after import' is ticked' clear the currently selected images list and add the newly imported

## Main Window

The main window is opened on the apps launch and contains the main menu and a full window sized display of the focused image.

### Menu Bar

The main menu toolbar at the top with the following menus:

- File
  
  - New Project
  
  - Open Project
  
  - Recent Projects
  
  - Save As
  
  - Import Images

- Edit
  
  - Preferences

- Windows
  
  - Gallery
  
  - Filter
  
  - Tag
  
  - Export

- Help
  
  - Documentation

### Image Display

A full window sized display of the currently focused image, no navigation buttons, filenames or likewise. If no image is currently focuses a button is shown to launch the gallary window



## Gallery

The gallery is launched from the 'window' menu and is the primary method for navigating images contained within the project. It shows a list of of all the images contained within the project after filters have been applied showing:

- A small thumnail of the image with the size settable by a slider below the list.

- The name of the images from the .json

- A tickbox allowing the image to be added/removed from the selection

The following actions have the following effects:

- Clicking an image will make it the active image and is shown on the full image display. 

- Pressing the up and down arrows changes the active image selection

- Pressing spacebar will add the active image to the selection

- Pressing 'c' will remove the image from the selection

At the bottow of the list are buttons for:

- 'select all': selects all currently listed images

- 'remove all' removes all currently selected images

- 'size': slider to set thumbnail size

The images that are selected by the gallary determin which images actions by other tools are acted on. If no images are selected then the active image is acted on. If any images are selected then only them images are acted on.

Note that if the filter tool subsiquently removes images from the gallary list that have been selected these images become unselected, ie there is no selection memory. Once an image has been removed from the gallary list if it is re added it is no longer selected.

## Filter

Allows the images in the gallary to be filtered based on a criteria provided by a single string. The these filter strings can be saved into the project.json for quick reuse. The window contains:

- A string entry for the filter criteria

- button "save filter"

- list of saved filters which when clicked are copyed to the filter string box. A 'x' at the end of each string allows it to be deleted.

The filter string uses simple logical statements like:

- tag1 AND tag2 NOT tag3

When writing starts a dropdown list is shown of already used tags in the project that are simerlar to what is been typed. This uses fuzzy logic where tags are listed in the format 'category:tag'. Pressing the up or down arrows navigates through simerlar tags and hitting tab accepts the current selected tag. The user can containue to add more logical condiitons and tags without neededing to use the mouse in any way. The gallary updates automatly as conditions filter conditions are added.

## Tag

This allows both viewing and setting of tags. If no images are selected then the active image is used or if any images are selected then all the combined unique tags in them images are shown. The window shows in order:

- An entry field for a new tag

- A list of the tags in the selected images 

Each list line behaves the same way when interacted with:

- clicking on any line alows the value to be edited

- using the up and down arrows navigates between the tags in the list

- deleteing all the text for an exsisting tag removes that tag from all selected images

- if a tag is modified all instances of that tag in the selected images are modified

- when text is written a fuzzy search is perfomed that populates a drop down of simerlar tags in the project which can be selected with the up and down arrows and tab to accept

The entry field behaves like this:

- Selecting the entry line allow text to be written

- When writing text a fuzzy search is perfomed as above

- Hitting enter adds the tag to the bottom of the list and clears the new line for entry of another tag.

- Hitting the up and down arrows with no text entered changes the active image in the gallary.

### Export

This sets which tags are to be written to the caption.txt files and the window shares a simerlar layout to the filter window:

- A string entry for the export profile

- button "save profile"

- list of saved profiles which when clicked are copyed to the profile string box. A 'x' at the end of each string allows it to be deleted.

- A preview of the caption to be exported for the active image.

- button 'export selected'

The profiles are set using the following string format where curly braces are substituded with tags from the stated category:

- trigger, {class}, {camera}, {details}[0:3]

the additions of square brackets uses the python range notation to specify how many to include from the specified category.

Pressing export selected writes out the export profile










