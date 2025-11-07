---
{}
---

# Stringing Prevention

## Problem Description
Stringing in 3D printing is a defect where thin unwanted threads or "strings" of filament are left between different parts of a print. These appear as fine wisps or hairs connecting areas that should be separate, degrading print quality and surface finish. Stringing occurs because molten filament continues to ooze out of the nozzle during non-extruding travel moves.

## Common Causes
- **Insufficient Retraction:** Filament is not pulled back enough during travel moves, allowing molten plastic to drip.
- **Excessively High Nozzle Temperature:** High temperatures make filament more fluid and prone to oozing.
- **Slow Travel Speed:** Longer travel moves give filament more time to ooze out.
- **Wet or Poor Filament:** Filament that absorbed moisture creates steam bubbles and inconsistent extrusion.
- **Nozzle Dragging on Print:** Lack of Z-hop or combing settings causes the nozzle to drag and pull strings.
- **Material Properties:** Some materials like PET-G are naturally stickier and more prone to stringing.

## Solutions
1. **Enable and Tune Retraction Settings:**  
   - Turn on retraction if disabled.  
   - Increase retraction distance gradually (start ~2-5 mm for Bowden setups; less for direct drive).  
   - Increase retraction speed (25-50 mm/s is typical).  
   - Enable Z-hop (lift nozzle during travel moves) to reduce dragging strings.  
2. **Lower Nozzle Temperature:**  
   - Reduce temperature in 5-10°C increments until stringing improves without compromising layer adhesion.  
   - Use temperature tower tests to find optimal temperature per filament.  
3. **Increase Travel Speed:**  
   - Increase non-print travel speed (~150-200 mm/s) to reduce ooze time during moves.  
4. **Keep Filament Dry:**  
   - Store filament in dry places or use filament dryers.  
   - Bake filament at 50-60°C to remove moisture if needed.  
5. **Enable Combing Mode:**  
   - Use slicer combing to keep travel moves within infill areas, reducing stringing risk.  
6. **Optimize Print Speed and Cooling:**  
   - Adjust print speed and ensure proper cooling fans are active for quick solidification (especially for PLA).  
7. **Coasting and Pressure Advance:**  
   - Use coasting (stop extrusion slightly before end of segment) to reduce internal nozzle pressure preventing ooze.  
   - Some advanced firmware allow pressure advance tuning.

## Prevention
- Use good-quality filament with low moisture content.  
- Store filament properly in dry or airtight containers with desiccant.  
- Regularly calibrate retraction and temperature settings for each filament type you use.  
- Use slicer features like combing, Z-hop, and pressure advance to limit ooze.  
- Maintain your nozzle clean and unclogged for consistent extrusion.

## Settings to Adjust
| Setting             | Recommended Range / Tips                   |
|---------------------|-------------------------------------------|
| Retraction Distance | 2-5 mm (Bowden); 0.5-2 mm (Direct Drive) |
| Retraction Speed    | 25-50 mm/s                                |
| Nozzle Temperature  | PLA: 180-210°C; ABS: 210-250°C; PET-G: 220-250°C |
| Travel Speed        | 150-200 mm/s                             |
| Z-Hop               | Enable and set 0.2-0.5 mm                 |
| Combing Mode        | Enable on slicer to reduce travel across open spaces |
| Cooling Fan Speed   | PLA: 100% after first layers; PETG: 50-70% |
| Coasting            | Enable if supported, start small value    |

## Visual Indicators
- Fine thin threads or "hairs" visible between print parts or on the surface.  
- Wispy filament strands bridging gaps or holes.  
- Surface appears fuzzy or less smooth in some areas.

## References
- eufyMake: 3D Print Stringing Causes and Fixes[1]  
- FacFox Docs: Retraction and Temperature Adjustments[2]  
- 3DGearZone: Retraction and Temperature Tips[3]  
- Unionfab Blog: Retraction, Temperature, and Speed Adjustments[4]  
- QIDI Tech Blog: Retraction, Travel Speed, and Cooling[5]  
- Anycubic Store Guide: Temperature and Speed Balance[6]  
- All3DP: Retraction as Primary Solution[7]  
- JLC3DP: Drying Filament and Combing Settings[8]  
- Simplify3D Troubleshooting: Retraction Importance[9]