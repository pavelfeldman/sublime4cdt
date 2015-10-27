# sublime4cdt

# Configuration

Add a `.devtools` file to the root of the project. Source should be something like this:

```json
{
    "mappings": [
        { "folder": "/src/web/", "url": "http://localhost:8080/" }
    ],

    "excludes": [
        "/src/web/Images/"
    ]
}
```
* Mapping folder location must begin with `/`. The path is considered relative to the `.devtools` file.
* DevTools will exclude the following pattern by default:
`/\.devtools|/\.git/|/\.sass-cache/|/\.hg/|/\.idea/|/\.svn/|/\.cache/|/\.project/|/\.DS_Store$|/\.Trashes$|/\.Spotlight-V100$|/\.AppleDouble$|/\.LSOverride$|/Icon$|/\._.*$`
