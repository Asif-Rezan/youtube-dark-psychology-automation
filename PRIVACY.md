# Dudi Dam TV privacy information

Dudi Dam TV is the channel owner's personal kids rhyme production automation. It is not a public sign-in service.

The automation uses Google authorization to identify the selected YouTube channel, upload and inspect its music videos, set thumbnails, and create and manage its own media/checkpoint files in Google Drive. Separate authorizations are used for YouTube and Drive. It does not request access to Gmail, contacts, or unrelated Drive files.

OAuth credentials are kept outside source control and are intended to be stored in encrypted GitHub Actions secrets. They are used only with Google's APIs. Original lyrics and scene descriptions are written by the pinned local Qwen model. Compact verse and story history is retained privately in the dedicated Drive folder to check future songs for repetition. Original lyrics and music are generated on GitHub Actions CPU runners. Public model files are downloaded from Hugging Face; no lyrics, musical prompts, or Google credentials are sent to a hosted model inference service.

Generated lyrics, audio, thumbnails and video may be retained as GitHub workflow artifacts for seven days. The intended final music videos are published publicly to the owner's selected YouTube channel. Drive checkpoints remain private to their owner. When publishing is enabled, verified published media is deleted from the dedicated private Drive folder through an exact-file cleanup journal; state and history remain. The owner can remove stored media, delete repository secrets, or revoke Google authorization through their Google Account permissions at any time.

The automation does not sell Google user data or use it for advertising or model training. Its use of Google API information is subject to the Google API Services User Data Policy, including Limited Use requirements. Google's, GitHub's and Hugging Face's respective service policies also apply to their services.

For questions, contact the project owner through this repository.
