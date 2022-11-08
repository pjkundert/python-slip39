from tkinter import Tk, font
import  PySimpleGUI as sg
root = Tk()
font_tuple = font.families()
#Creates a Empty list to hold font names
FontList=[]
fonts = [font.Font(family=f) for f in font.families()]
monospace = (f for f in fonts if f.metrics("fixed"))
# for font in font_tuple:
#     FontList.append(font)
for font in monospace:
    FontList.append(font.actual('family'))
root.destroy()
print( '\n'.join( FontList ))

#size 28, 28 is optimized for my Android phone please tweak as per your screen
#Scrolled popup to accommodate big list
sg.popup_scrolled(FontList, title='All fonts installed using PySimpleGUI', size=(28,28), grab_anywhere=True)

