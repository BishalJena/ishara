interesting piece of sign language The ASSIST Project by ai4bharat funded by
microsoft: https://sign-language.ai4bharat.org/#/ google's sign-to-text for
ASL, for pixel devices
only:https://support.google.com/pixelphone/answer/17468449?hl=en isl
translate:dataset for translating
isl:https://github.com/exploration-lab/isltranslate huggingface find using the
above dataset:https://huggingface.co/datasets/pedroodb/glosl-isl old hugginface
model:https://huggingface.co/cdsteameight/ISL-SignLanguageTranslation isl to
character kaggle
dataset:https://www.kaggle.com/datasets/mrigaankjaswal/indian-sign-language-to-characters-dataset
ISL-CSLTR: Indian Sign Language Dataset:
https://www.kaggle.com/datasets/drblack00/isl-csltr-indian-sign-language-dataset
iSign: A Benchmark for Indian Sign Language
Processing:https://huggingface.co/papers/2407.05404
SignLink-ISL:https://github.com/Naneet/SignLink-ISL reddit post for
above:https://www.reddit.com/r/learnmachinelearning/comments/1hpocgy/feedback_needed_indian_sign_language_recognition/
INCLUDE: A Large Scale Dataset for Indian Sign Language Recognition:
https://zenodo.org/records/4010759
https://dl.acm.org/doi/10.1145/3394171.3413528, also found that they transfer
learny from ASL aswell google's google/siglip2-base-patch16-224:
https://huggingface.co/google/siglip2-base-patch16-224,
https://huggingface.co/papers/2502.14786,
https://github.com/google-research/big_vision/blob/main/big_vision/configs/proj/image_text/README_siglip2.md
Hindi-Sign-Language-Detection: https://huggingface.co/prithivMLmods/Hindi-Sign-Language-Detection



Several models, classification tools, and datasets for Indian Sign Language
(ISL) are available on Hugging Face:



Models & Detection • cdsteameight/ISL-SignLanguageTranslation: A
Keras/TensorFlow model trained to recognize Indian Sign Language from video
datasets. • Hemg/Indian-sign-language-classification: An image classification
model built with Transformers to classify ISL signs. •
prithivMLmods/Hindi-Sign-Language-Detection: An image classification pipeline
for sign language detection. [1]
(https://huggingface.co/cdsteameight/ISL-SignLanguageTranslation), [2]
(https://huggingface.co/Hemg/Indian-sign-language-classification), [3]
(https://huggingface.co/prithivMLmods/Hindi-Sign-Language-Detection) Datasets &
Benchmarks • Exploration-Lab/iSign: A large-scale benchmark and video-English
dataset featuring over 118,000 video-sentence/phrase pairs for ISL processing.
• Exploration-Lab/CISLR: A corpus for word-level Indian Sign Language
recognition using video clips. • bridgeconn/sign-dictionary-isl: A sign
dictionary dataset containing ISL video clips with individual gloss
annotations. • silentone0725/Indian_Sign_Language_Data.gov_Rencoded: Encoded
video clips based on the Indian Sign Language Dictionary from the ISLRTC. •
ISLTranslate Paper: A research paper introducing a transformer-based model and
translation dataset for continuous Indian Sign Language. [1]
(https://huggingface.co/datasets/Exploration-Lab/CISLR), [2]
(https://huggingface.co/datasets/Exploration-Lab/iSign), [3]
(https://huggingface.co/papers/2407.05404), [4]
(https://huggingface.co/datasets/bridgeconn/sign-dictionary-isl), [5]
(https://huggingface.co/datasets/silentone0725/Indian_Sign_Language_Data.gov_Rencoded),
[6] (https://huggingface.co/papers/2307.05440) If you are looking for a
specific task—like video-to-text recognition, gloss translation, or loading a
model via PyTorch/Keras—let me know and I can provide the exact code snippet.
