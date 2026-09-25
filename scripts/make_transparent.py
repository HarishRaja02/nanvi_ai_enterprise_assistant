from PIL import Image

def make_transparent():
    img = Image.open('frontend/public/nanvi-n-icon.png').convert('RGBA')
    datas = img.getdata()

    newData = []
    for item in datas:
        # If pixel is white or near white, make transparent
        if item[0] > 225 and item[1] > 225 and item[2] > 225:
            newData.append((255, 255, 255, 0))
        else:
            newData.append(item)

    img.putdata(newData)
    img.save('frontend/public/nanvi-n-icon.png', 'PNG')
    img.save('frontend/src/assets/nanvi-n-icon.png', 'PNG')
    print('Transparent icon saved!')

if __name__ == '__main__':
    make_transparent()
