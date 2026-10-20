# Original research links

The original collection of Indian Sign Language (ISL) and American Sign Language
(ASL) research leads, organized for sharing. For evaluated findings and current
recommendations, start with the [research index](README.md).

## Projects and product references

- **AI4Bharat ASSIST Project** — [Project website](https://sign-language.ai4bharat.org/#/).
  The original notes identify Microsoft funding.
- **Google Pixel sign-to-text for ASL** — [Google support article](https://support.google.com/pixelphone/answer/17468449?hl=en).
- **SignLink-ISL** — [GitHub repository](https://github.com/Naneet/SignLink-ISL)
  and [author's Reddit feedback post](https://www.reddit.com/r/learnmachinelearning/comments/1hpocgy/feedback_needed_indian_sign_language_recognition/).

## Datasets and benchmarks

- **INCLUDE: A Large Scale Dataset for Indian Sign Language Recognition** —
  [Dataset on Zenodo](https://zenodo.org/records/4010759) ·
  [Paper](https://dl.acm.org/doi/10.1145/3394171.3413528).
- **CISLR** — Word-level ISL video corpus:
  [Hugging Face dataset](https://huggingface.co/datasets/Exploration-Lab/CISLR).
- **iSign: A Benchmark for Indian Sign Language Processing** —
  [Hugging Face dataset](https://huggingface.co/datasets/Exploration-Lab/iSign) ·
  [Paper](https://huggingface.co/papers/2407.05404).
  The original notes describe over 118,000 video–sentence/phrase pairs.
- **ISLTranslate** — Continuous ISL translation research:
  [GitHub repository](https://github.com/exploration-lab/isltranslate) ·
  [Paper](https://huggingface.co/papers/2307.05440).
- **GLOSL-ISL** — [Hugging Face dataset](https://huggingface.co/datasets/pedroodb/glosl-isl),
  originally found while exploring ISLTranslate.
- **Indian Sign Language to Characters** —
  [Kaggle dataset](https://www.kaggle.com/datasets/mrigaankjaswal/indian-sign-language-to-characters-dataset).
- **ISL-CSLTR: Indian Sign Language Dataset** —
  [Kaggle dataset](https://www.kaggle.com/datasets/drblack00/isl-csltr-indian-sign-language-dataset).
- **ISL sign dictionary — bridgeconn** — Video clips with individual gloss annotations:
  [Hugging Face dataset](https://huggingface.co/datasets/bridgeconn/sign-dictionary-isl).
- **Indian Sign Language Dictionary, re-encoded — silentone0725** —
  [Hugging Face dataset](https://huggingface.co/datasets/silentone0725/Indian_Sign_Language_Data.gov_Rencoded).
  Originally noted as re-encoded clips from the ISLRTC dictionary.

## Model listings

- **ISL-SignLanguageTranslation — cdsteameight** —
  [Hugging Face model](https://huggingface.co/cdsteameight/ISL-SignLanguageTranslation).
  Originally described as a Keras/TensorFlow model for ISL video recognition.
- **Indian sign language classification — Hemg** —
  [Hugging Face model](https://huggingface.co/Hemg/Indian-sign-language-classification).
  Originally described as an image classifier built with Transformers.
- **Hindi-Sign-Language-Detection — prithivMLmods** —
  [Hugging Face model](https://huggingface.co/prithivMLmods/Hindi-Sign-Language-Detection).
  Originally described as an image-classification pipeline for sign detection.

## Pretrained encoders and transfer learning

- **Google SigLIP 2** —
  [Base model checkpoint](https://huggingface.co/google/siglip2-base-patch16-224) ·
  [Paper](https://huggingface.co/papers/2502.14786) ·
  [Implementation documentation](https://github.com/google-research/big_vision/blob/main/big_vision/configs/proj/image_text/README_siglip2.md).

The original notes also raised ASL-to-ISL transfer as a research direction.
See the later [ASL transfer review](recognition/asl-transfer.md) for the findings.
