import fitz,os
pdf=fitz.open("rotations/testh180.pdf")
def getCoords(bbox):
    return(round(bbox[0]/72,2),round(bbox[1]/72,2),round(bbox[2]/72,2),round(bbox[3]/72,2))
def correctedBbox(rotation,bbox,bound):
    width=bound[2]
    height=bound[3]
    x1,y1,x2,y2=bbox
    if(rotation==90):# x1: 11-b2; y1: a1; x2: 11-b1; y2: a2
        return(width-y2,x1,width-y1,x2) #792 = 11 inch * 72 pixels/inch
    if(rotation==180):# x1:8.5-a2; y1: 11-b2; x2:8.5-a1; y2:11-b1
        return(width-x2,height-y2,width-x1,height-y1)
    elif(rotation==270):# x1:b1 ; y1:11-a2 ; x2:b2 ; y2:11-a1
        return(y1,height-x2,y2,height-x1)
    else:return(bbox)
def intersecting(bbox,drawing):
    if((bbox[0]>=drawing[2]) or (bbox[1]>=drawing[3]) or (bbox[2]<=drawing[0]) or (bbox[3]<=drawing[1])):return(False)
    else:return(True)    
for p in pdf:
    print(p.rotation,p.bound())
    drawings=[d for d in p.get_drawings()
                    if (d['rect'][2]-d['rect'][0]>4)
                    and (d['rect'][3]-d['rect'][1]>4)
                    and (d['fill']==[0])]
    blocks=p.getText("rawdict")['blocks']
    """print("Drawings:\n")
    for d in drawings:
        print(round(d['rect'][0]/72,1),round(d['rect'][1]/72,1),round(d['rect'][2]/72,1),round(d['rect'][3]/72,1))
    print("\nSpans:\n")
    for b in blocks:
        if('lines' in b):
            for line in b['lines']:
                for span in line['spans']:
                    print(round(span['bbox'][0]/72,1),round(span['bbox'][1]/72,1),round(span['bbox'][2]/72,1),round(span['bbox'][3]/72,1))"""
    for block in blocks:
        if('lines' in block):
            for line in block['lines']:
                for span in line['spans']:
                    #for d in drawings:
                        #if(intersecting(span['bbox'],d['rect'])):
                    text=""
                    for char in span['chars']:
                        text+=char['c']
                    #print("Drawing:",round(d['rect'][0]/72,1),round(d['rect'][1]/72,1),round(d['rect'][2]/72,1),round(d['rect'][3]/72,1))
                    print("Span:"+" "+str(getCoords(span['bbox']))+"\t"+text+" "+str(getCoords(correctedBbox(p.rotation,span['bbox'],p.bound()))))
