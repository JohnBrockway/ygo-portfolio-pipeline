# ygo-portfolio-pipeline
Scheduled job to be run regularly that populates/updates a master set of Yu-Gi-Oh! cards and sets in cloud hosting. This set is digested by a web app hosted at TBD.

Data is pulled from [Yugipedia](https://yugipedia.com/wiki/Yugipedia) via the MediaWiki API. This project was influenced by, although not a fork of, the [yaml-yugi](https://github.com/DawnbrandBots/yaml-yugi) collection of repositories; that source is a more comprehensive dataset, where this one is focused on a more limited, personalized use-case.

All content original to Yugipedia is licensed under the [Creative Commons Attribution-ShareAlike 4.0 International License](https://creativecommons.org/licenses/by-sa/4.0/deed.en). Content of *Yu-Gi-Oh!* cards themselves is © 2020 Studio Dice/Shueisha, TV Tokyo, Konami. Code, and any other remaining content that is original to this repository, falls under the [GNU General Public License 3.0 (or later)](https://www.gnu.org/licenses/gpl-3.0.en.html) (see [license.txt](/license.txt))
