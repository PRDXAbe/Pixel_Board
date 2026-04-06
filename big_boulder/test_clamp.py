def clampToGap(px, py, cw, ch, placementAxis, supportWFrac=0.56, supportHFrac=0.60, boardWFrac=0.38, boardHFrac=0.40):
    cx = cw / 2.0
    cy = ch / 2.0
    gapMidX = cw * ((supportWFrac + boardWFrac) / 4.0)
    gapMidY = ch * ((supportHFrac + boardHFrac) / 4.0)
    
    if placementAxis == "VERTICAL":
        x = cx
        snapToTop = py < cy
        y = cy - gapMidY if snapToTop else cy + gapMidY
        return (x, y)
    else:
        y = cy
        snapToLeft = px < cx
        x = cx - gapMidX if snapToLeft else cx + gapMidX
        return (x, y)

print("VERTICAL (bottom drag)", clampToGap(500, 600, 1000, 1000, "VERTICAL"))
print("HORIZONTAL (right drag)", clampToGap(600, 500, 1000, 1000, "HORIZONTAL"))
