# Identify Game Project

This project is designed to identify games based on executable files, extract relevant metadata, and search for game information using various APIs. The scripts are modularized for better organization and maintainability.

## Project Structure

```
identify_game
├── src
│   ├── main.sh                # Entry point for the script, orchestrates execution
│   ├── slug_generation.sh      # Functions for generating slugs from executable names
│   ├── metadata_extraction.sh  # Functions for extracting metadata from executables
│   ├── config_extraction.sh    # Functions for extracting information from config files
│   ├── game_search.sh          # Functions for searching games using APIs
│   └── utils.sh                # Utility functions used across scripts
├── variables.txt               # Text file for storing variables and important information
└── README.md                   # Documentation for the project
```

## Setup Instructions

1. **Clone the Repository**: 
   Clone this repository to your local machine using:
   ```
   git clone <repository-url>
   ```

2. **Navigate to the Project Directory**:
   ```
   cd identify_game
   ```

3. **Install Dependencies**:
   Ensure that the following dependencies are installed on your system:
   - `jq`
   - `curl`
   - `zenity`
   - `exiftool` (if using metadata extraction)

4. **Configure Variables**:
   Edit the `variables.txt` file to set any necessary configuration variables.

## Running the Script

To run the script, execute the following command in your terminal:
```
bash src/main.sh
```

## Functionality Overview

- **Slug Generation**: The `slug_generation.sh` script contains multiple methods for generating slugs from executable names, ensuring proper formatting and cleaning.
  
- **Metadata Extraction**: The `metadata_extraction.sh` script utilizes tools like `strings` and `exiftool` to extract relevant metadata from executable files.

- **Configuration Extraction**: The `config_extraction.sh` script searches for specific keys in various configuration file formats to retrieve game-related data.

- **Game Search**: The `game_search.sh` script performs searches for games using APIs from RAWG, Lutris, and SteamDB, processing the results accordingly.

- **Utilities**: The `utils.sh` script contains common utility functions that are used across the other scripts for tasks such as cleaning names and handling errors.

## Contribution

Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.