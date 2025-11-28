Ideal prompts for Zoo’s Text‑to‑CAD are short, specific mechanical design specs: think “clean manufacturing drawing described in one sentence,” not a story or conversation.[1][2][3] The “perfect” prompt nails geometry, key dimensions, relationships, and intent, while staying concise enough that the model does not have to guess much.[1][2]

## What a strong prompt includes

For best results, each prompt should explicitly cover:[1][2][3]

- Part type and role: bracket, flange, plate, spacer, gear, handle, etc., plus how it’s used (mounting, supporting, aligning).  
- Main shape and operations: block, cylinder, L‑bracket, through‑holes, counterbores, slots, fillets, chamfers, ribs, bosses.[2]
- Critical dimensions: overall length/width/height or diameter/thickness, plus any must‑have distances (hole spacing, offsets, clearances).[1][2]
- Hole/fastener details: count, diameter, pattern (e.g., bolt circle, rectangular grid), countersink/counterbore, intended fastener size.[2]
- Symmetry and alignment: centered vs. offset, mirrored about which axes, constraints like “holes equally spaced around the circle.”[2]
- Application/constraints: load direction, mating parts, manufacturability concerns if important (e.g., “printable on FDM with no supports”).[2][4]

Zoo explicitly recommends concise prompts (1–2 sentences) with clear dimensions; longer prompts are supported but slower and more failure‑prone.[1][2][3] If you omit key dimensions, the system fills them using typical industry assumptions, which can drift from what you actually want.[1][2][3]

## Characteristics of the “perfect” Zoo prompt

A high‑performing Text‑to‑CAD prompt generally has these characteristics:[1][2][3]

- Concise: One or two well‑structured sentences, not a paragraph of prose.  
- Structured: Flows from overall part → key dimensions → features → relationships (e.g., “overall body, then holes, then fillets”).  
- Quantitative: Uses concrete numbers and units (mm, in) instead of “small/large/roughly.”  
- Deterministic: Avoids ambiguous words like “about,” “kinda,” “robust,” unless you truly don’t care.  
- Mechanically oriented: Sticks to mechanical parts and clear operations, which is what the system is tuned for.[2][4]
- Single intent: Describes one part at a time rather than an assembly or multiple variants in one prompt.[2]

Example of a “good” pattern (you would adapt dimensions/intent):  
> “An L‑shaped steel bracket, 100×50×5 mm, with two 8 mm through‑holes on the long leg and one 8 mm hole on the short leg, sized for M8 bolts, holes centered 15 mm from each edge and filleted 5 mm on all external corners.”  

## Designing a user Q&A flow

Your UI should collect structured inputs, then synthesize a single prompt string for Zoo. Use a brief form rather than free text whenever possible.[5][6] Core questions to ask:  

1. **Part type and usage**  
   - “What are you making?” (dropdown: bracket, plate, flange, spacer, adapter, gear, other)  
   - “What does it attach to or support?” (text, but encourage concise functional description)  

2. **Overall envelope / base geometry**  
   - For plates/brackets: overall length, width, thickness, units.  
   - For cylindrical parts: outer diameter, height/length, inner diameter if hollow.  

3. **Mounting and holes**  
   - “How many holes?”  
   - “What diameter and for what fastener size?”  
   - “Where should they be?” (pattern options: centered, on a bolt circle with diameter X, rectangular grid, along an edge at spacing Y)  

4. **Constraints and features**  
   - “Any fillets/chamfers? If yes, radius/size and where?”  
   - “Any slots, cutouts, ribs, or bosses? Briefly describe.”  

5. **Tolerance / flexibility**  
   - “Are any dimensions flexible?” (checkboxes beside fields, or a simple: “Can Zoo choose sensible defaults where unspecified?”)  

Your backend then assembles these into a single, well‑structured sentence or two, prioritizing the non‑flexible dimensions and features. That keeps user input ergonomic while still giving Text‑to‑CAD a highly specific, mechanically grounded prompt aligned with the documented best practices.[1][2][3]

Sources
[1] Text-to-CAD - zoo.dev https://zoo.dev/docs/zoo-design-studio/text-to-cad
[2] Text-to-CAD: Generating Editable, Parametric B-Rep CAD Models ... https://zoo.dev/research/introducing-text-to-cad
[3] Frequently Asked Questions - zoo.dev https://zoo.dev/docs/faq
[4] Introducing Text-to-CAD - zoo.dev https://zoo.dev/blog/introducing-text-to-cad
[5] Text-to-CAD Tutorial - zoo.dev https://zoo.dev/docs/developer-tools/tutorials/text-to-cad
[6] A lightweight UI for interacting with the Zoo Text-to-CAD API. - GitHub https://github.com/KittyCAD/text-to-cad-ui
[7] ML CAD Model Generator | Create CAD Files With Text | Zoo - zoo.dev https://zoo.dev/text-to-cad
[8] Zoo Design Studio: Text-to-CAD Basics - YouTube https://www.youtube.com/watch?v=yugPWyrE_AE
[9] Generate a CAD model from text - zoo.dev https://zoo.dev/docs/developer-tools/api/ml/generate-a-cad-model-from-text
[10] Creating from scratch using Text-to-CAD | Zoo Design Studio https://www.youtube.com/watch?v=Syz4NHyMwK0
[11] If you use CAD, try this! : r/3Dprinting - Reddit https://www.reddit.com/r/3Dprinting/comments/1bshptz/if_you_use_cad_try_this/
[12] Convert text into CAD through this Text-to-CAD product : r/Design https://www.reddit.com/r/Design/comments/1brnxsz/convert_text_into_cad_through_this_texttocad/
[13] Mind-Blowing AI Creates 3D CAD Models With Simple Text - YouTube https://www.youtube.com/watch?v=GI-Pp-_ioFE
[14] Zoo Text-to-CAD UI - Software - Carbide 3D Community Site https://community.carbide3d.com/t/zoo-text-to-cad-ui/89536
[15] Text to CAD with zoo.dev - NextAITools - Reddit https://www.reddit.com/r/NextAITools/comments/1hrpyrz/text_to_cad_with_zoodev/
[16] Text to CAD? - Mechanomy https://mechanomy.com/posts/240205_textToCAD/
[17] Unlock the Power of Text-to-CAD: Expert Tips for Success - Instagram https://www.instagram.com/reel/DPPHtDvgrz8/
[18] Intro to Text-to-CAD | Zoo Design Studio - YouTube https://www.youtube.com/watch?v=mm7G_P1ac_U
[19] Text2CAD: Generating Sequential CAD Models from Beginner-to ... https://arxiv.org/html/2409.17106v1
