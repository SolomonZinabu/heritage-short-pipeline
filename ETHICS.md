# Ethics, consent, licences, and labelling

## Consent
No real person's face, likeness, or voice may be generated or used until informed consent for this use is recorded. Store sensitive consent documents privately; record a non-sensitive status/reference here.

Two real people appear in this film. Both agreed to it before any picture of them was made.

| Person / asset | Face, likeness, or voice | Consent status and date | Scope |
|---|---|---|---|
| Solomon Zinabu, the film-maker. He is the boy in the story. | His own face as a child, taken from a childhood photograph. | Consented on 25 Nov 2026. He stated it himself, and he directs the film. | His likeness, generated from the photograph, as the boy in this film: in the repository, in the work submitted to the programme, and in the public post. |
| His mother | Her face, taken from her photograph. | Consented on 25 Nov 2026. This is recorded as her son stated it: "both of us are consented and we are okay to be on the video". | Her likeness, generated from the photograph, as the mother in this film, for the same uses. |

- **No real voice is used.** The narrator is a synthetic voice. Nobody's voice is cloned, and the mother's one line is quoted by the narrator from the story as her son tells it.
- **Before the public post: the mother's own words.** On 26 Nov 2026 her son reported that she watched the film and liked it. Her confirmation in her own words, that it may be posted publicly, is still to be written here.
- **The photographs are not published.** The two source photographs stay off the repository, and so do the small copies that were made from them for the first version. The film's pictures are the film-maker's own, in `keyframes/`. They carry no location or device data.
- **The likeness is an approximation.** The people in the film are drawn by an image model; they are not photographs. The first set of pictures was made by a small model from the two photographs. The film-maker rejected it, because the people did not look Ethiopian. He then made the pictures himself, with an image tool of his own choice: the people are Habesha with dark brown skin, and the mother has her glasses, her white netela and her blue-flowered dress. **The pictures were made by the film-maker with ChatGPT, from OpenAI.** He said so on 26 Nov 2026. Which image model ChatGPT used is not stated by OpenAI, and whether he gave it the photographs as references is not recorded here. The pipeline no longer reads the photographs, and neither they nor the first version's copies of them are published.

## Models and output terms
| Model / provider | Version | Licence / terms checked | Notes |
|---|---|---|---|
| FLUX.2 [klein], Cloudflare Workers AI | `@cf/black-forest-labs/flux-2-klein-4b` | Apache 2.0. Cloudflare states that it does not use what customers send to Workers AI to train its models. Read on 25 Nov 2026. | Made the pictures of the first version, which the film-maker rejected. It does not make the pictures of this film. It received the cropped photographs as reference images, with each request of that version. Free allowance of 10,000 Neurons a day. |
| Gemini 3.8 Flash TTS, Google AI Studio | `gemini-3.8-flash-tts` | Free tier. Google's terms say it may use what is submitted to improve its products, and that human reviewers may read it. Read on 25 Nov 2026. | Speaks the narration. Receives only the narration lines. 10 requests a day on the free tier, as the service itself stated on 25 Nov 2026. |
| ChatGPT, OpenAI | the image feature of ChatGPT; OpenAI does not state which image model it uses | OpenAI's Terms of Use, read on 26 Nov 2026: "you (a) retain your ownership rights in Input and (b) own the Output"; "output may not be unique and other users may receive similar output from our Services"; a user must not "Represent that Output was human-generated when it was not". | Made the pictures of this film, at the film-maker's own hand and outside the pipeline, on his own account. The film says it was made with AI, on its end card and in a note inside each file. |
| ACE-Step 1.5 | `acestep-v15-turbo`, from the official repository | MIT. Read on 25 Nov 2026. | Makes the score, on Kaggle's free GPU. Receives only the music caption. It is instrumental, so no voice is generated. |
| FFmpeg | 9.0.2, the `gyan.dev` essentials build, through `imageio-ffmpeg` 0.8.1 | GNU GPL version 3, as the program itself reports (`ffmpeg -L`). `imageio-ffmpeg` is BSD-2-Clause. | Cuts the film together. Not a generative model. |
| Pillow | 11.3.0 | MIT-CMU, as the package reports. | Draws the subtitles and the end card. |

Not used: Wan 2.2, for moving shots, has not been run for this film. If it is, its terms will be added here.

## Labelling
- **AI end card included: yes.** The last three seconds of the film read "Made with AI" and, in Amharic, "ይሄ ፊልም በሰው ሰራሽ አስተውሎት ተሰርቷል" ("This film was made with artificial intelligence"). It is written by `pipeline/subtitles.py` and laid over the last frame by `pipeline/assemble.py`, which counts the film's frames to make sure the card is there. It has been checked on dry runs. It is to be checked once more on the finished film.
- **A note inside the file: yes.** Each film file carries its title and this comment in its metadata: "Made with AI. The pictures, the narration and the music were generated by models. The two people appear with their consent." Read back from the radio cut on 25 Nov 2026.
- **Platform AI disclosure enabled: not yet.** No platform has been chosen. When the film is posted, the platform's own "made with AI" or "altered or synthetic content" label is to be switched on, and the post is to say it in words.
- **Watermarks / provenance metadata preserved: nothing to preserve.** The image service returns plain JPEG files. A search of its output on 25 Nov 2026 found no C2PA manifest, no Exif block and no comment. That is why the film carries the written note above. An invisible watermark, if one existed, could not have been found this way and would not survive the video encoding.
- **Private family details excluded from unreviewed endpoints: yes.** The narration and the prompts carry no names, addresses or other private details. The story's one exclamation, "Jesus of Nazareth!", is a saying, not a name. The photographs go to one service only, the one that states it does not train on them.

## What is real, and what is made
- **Real:** the two people themselves, as the film-maker knows them, and the story, in his own words.
- **Made:** every place and object in the pictures, the narration voice, the music, and the mother's one quoted line as it is spoken in the film.
- **Nobody is hurt.** The story is a comedy. The mother picks up a small stick and runs after her son, and both of them are laughing. No blow is shown or suggested.
