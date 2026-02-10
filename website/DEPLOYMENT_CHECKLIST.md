# 🚀 Deployment Checklist for Netlify

## Before You Deploy

### ✅ Step 1: Gather Your Files
Make sure you have:
- [ ] index.html (single page with everything)
- [ ] images/ folder with 10 images inside

### ✅ Step 2: Prepare Images Folder
Add these files to the `images` folder:

1. [ ] enxross_logo.jpg
2. [ ] empire.png
3. [ ] tokyo-dome.jpg
4. [ ] **kaizen_currents.png** - NEW! Your diagram
5. [ ] mike.jpeg
6. [ ] perm.jpeg
7. [ ] sho.jpeg
8. [ ] ray.jpeg
9. [ ] rabi.jpeg
10. [ ] anna.jpeg

**Important**: Filenames must match exactly (case-sensitive)

## Deploy to Netlify

### Method 1: Drag & Drop (5 minutes)

1. **Prepare Your Folder**
   - Folder contains:
     - index.html
     - images/ folder with all 10 images

2. **Go to Netlify**
   - Visit: https://app.netlify.com/drop
   - (Create free account if needed)

3. **Drop Your Folder**
   - Drag entire folder onto page
   - Netlify uploads and deploys
   - Get URL like: `https://random-name-123.netlify.app`

4. **Custom Domain (Optional)**
   - Site Settings → Domain Management
   - Add custom domain
   - Follow DNS instructions

### Method 2: GitHub + Netlify

1. **Upload to GitHub**
   - Create new repository
   - Upload index.html
   - Upload images/ folder

2. **Connect to Netlify**
   - https://app.netlify.com
   - "Add new site" → "Import project"
   - Choose GitHub
   - Select repository
   - Deploy!

3. **Future Updates**
   - Push to GitHub
   - Auto-deploys!

## After Deployment

### ✅ Test Checklist

1. [ ] Page loads correctly
2. [ ] All images show (no broken images)
3. [ ] All 10 images visible
4. [ ] **Kaizen Currents diagram shows**
5. [ ] Navigation links scroll to sections
6. [ ] "Schedule" link scrolls to schedule
7. [ ] Click January - accordion expands
8. [ ] Click February-June - all expand
9. [ ] FAQ accordions work
10. [ ] "Apply Now" button works
11. [ ] Social media links work
12. [ ] Works on mobile

### 🔍 Visual Check

**Images to verify:**
- [ ] enXross logo (top left)
- [ ] EmpireDAO logo (top left)
- [ ] Tokyo Dome photo
- [ ] **Kaizen Currents diagram** ⭐
- [ ] Mike's photo
- [ ] Perm's photo
- [ ] Sho's photo
- [ ] Ray's photo
- [ ] Rabi's photo
- [ ] Anna's photo

**Schedule Section:**
- [ ] Legend shows 5 badge types
- [ ] Weekly activities table visible
- [ ] 6 month accordions (Jan-June)
- [ ] Each month expands on click
- [ ] Tables show dates and events
- [ ] Color-coded badges display

## Troubleshooting

### Images Not Showing
**Solution**: 
- Check `images/` folder exists
- Verify exact filenames (case-sensitive)
- Example: `kaizen_currents.png` not `Kaizen_Currents.PNG`

### Schedule Not Expanding
**Solution**: 
- JavaScript is working (should be automatic)
- Try refreshing browser
- Clear cache

### Navigation Not Scrolling
**Solution**: 
- Links use #anchors (should work automatically)
- Check browser console for errors

## Final Structure

```
enxross-website/
├── index.html
└── images/
    ├── enxross_logo.jpg
    ├── empire.png
    ├── tokyo-dome.jpg
    ├── kaizen_currents.png  ← NEW!
    ├── mike.jpeg
    ├── perm.jpeg
    ├── sho.jpeg
    ├── ray.jpeg
    ├── rabi.jpeg
    └── anna.jpeg
```

## Need Help?

- Netlify Docs: https://docs.netlify.com
- Netlify Status: https://www.netlifystatus.com

---

**Ready? Add images and deploy!** 🚀
