import fitz,os,shutil
fitz.TOOLS.mupdf_display_errors(False)

def getCoords(bbox): # returns coordinates of a bbox
    return(round(bbox[0]/72,2),round(bbox[1]/72,2),round(bbox[2]/72,2),round(bbox[3]/72,2))

def correctedBbox(rotation,bbox,bound): # corrects the bboxes that have been messed up due to weird pdf rotations
    width=bound[2]
    height=bound[3]
    x1,y1,x2,y2=bbox
    if(rotation==90):
        return(width-y2,x1,width-y1,x2)
    if(rotation==180):
        return(width-x2,height-y2,width-x1,height-y1)
    elif(rotation==270):
        return(y1,height-x2,y2,height-x1)
    else:
        return(bbox)
    
def isIntersecting(bbox,drawing): # checks to see if a bbox intersects a drawing
    if((bbox[0]>=drawing[2]) or (bbox[1]>=drawing[3]) or (bbox[2]<=drawing[0]) or (bbox[3]<=drawing[1])):
        return(False)
    else:
        return(True)

def avgColor(pixMap): # returns the average color of a pixmap
    tot=0
    for c in range(0,pixMap.width):
        for r in range(0,pixMap.height):
            tot+=pixMap.pixel(c,r)[0]+pixMap.pixel(c,r)[1]+pixMap.pixel(c,r)[2]
    return tot/(pixMap.width*pixMap.height*3)

def isTextForRedaction(string): # checks to see if string is a common string used to redact text
    string=string.lower().replace(" ","")
    # below is a list of all the words I saw that replaced redacted text under the highlight
    for keyword in ["judgmentandprobationcommitmentorder","redactedandpubliclyfiled","nameredacted","redacted","redacte","redac","reda","red","re","multiple","multipl","multip","ultiple","confidential","privilege"]:
        if(keyword in string):
            string=string.replace(keyword,"")
    return(len(string)==0)

def hasDiffChars(string): # checks to see if a string contains the same characters (a common string used to redact text)
    string=string.lower().replace(" ","")
    for i in range(1,len(string)):
        if(string[i]!=string[0]):
            return(True)
    return(False)

def redactionFinder(file): # returns all of the improper redactions in a file
    redactions=[]
    try:
        pdf=fitz.open(file)
        currentPage=0
        for p in pdf:
            currentPage+=1
            searchPage=True
            try:
                d=[d for d in p.get_drawings()
                    if (d['rect'][2]-d['rect'][0]>4)
                    and (d['rect'][3]-d['rect'][1]>4)
                    and (d['fill']==[0])]
            except UnboundLocalError:
                searchPage=False
                pass
            if(searchPage):
                if(len(d)>0):
                    b=p.getText("rawdict")['blocks']
                    for block in b:
                        if('lines' in block):
                            for line in block['lines']:
                                text=""
                                printedText=""
                                for span in line['spans']:
                                    bbox=span['bbox']
                                    if((span['color']==0) and (bbox[3]>43)):    # 43 pixels is the farthest down the page I saw a header go (i.e. where one might find something along the lines of "Case #___")
                                        for char in span['chars']:
                                            for drawing in d:
                                                corrected=correctedBbox(p.rotation,char['bbox'],p.bound())
                                                if(isIntersecting(corrected,drawing['rect'])):
                                                    c=char['c']
                                                    pixMap=p.get_pixmap(clip=corrected)
                                                    if(pixMap.width!=0 and pixMap.height!=0):                                                      
                                                        color=avgColor(p.get_pixmap(clip=corrected))
                                                        if(color<85):
                                                            if(c.isnumeric() or c.isalpha() or c==" "):
                                                                text+=c
                                                            printedText+=c
                                                            break 
                                text=text.strip()
                                if((not isTextForRedaction(text)) and (hasDiffChars(text))):
                                    redactions.append([file,currentPage,bbox,printedText])
        pdf.close()
        return(redactions)
    except RuntimeError as error:
        pass

def printToPage(fromFolder,toFolder,filename): # prints the improper redactions from a file onto a text document
    file=os.path.join(fromFolder,filename)
    other=os.path.join(toFolder,filename+".txt")
    redactions=redactionFinder(file)
    if(redactions):
        f=open(other,"w")
        num=0
        for redaction in redactions:
            try:
                f.write(redaction[0]+", PAGE #"+str(redaction[1])+", Y: "+str(getCoords(redaction[2])[1])
                        +"–"+str(getCoords(redaction[2])[3])+"\t X: "+str(getCoords(redaction[2])[0])+"–"+str(getCoords(redaction[2])[2])+"\": ["+redaction[3]+"]\n")
                num+=1
            except UnicodeEncodeError:
                pass
        f.close()
        return(num)
    return(0)

def moveFilesToFolder(fromFolder,toFolder): # moves all of the files from the fromFolder to the toFolder that contain improper redactions
    for file in os.listdir(fromFolder):
        filepath=os.path.join(fromFolder,file)
        if(os.path.isfile(filepath)):
            num=printToPage(fromFolder,toFolder,file)
            if(num>0):
                shutil.copy(filepath,toFolder)
                print("File "+file+" found to have "+str(num)+" improper redactions")

fromFolder=input("Folder to search: ")
toFolder=input("Folder to move files with suspected redaction errors into: ")
moveFilesToFolder(fromFolder,toFolder)
