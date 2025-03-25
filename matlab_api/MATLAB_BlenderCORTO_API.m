function [strConfigJSON, ui8ImgSequence, charOutputPath, strOutputFilesList, charInputConfigDataPath] = MATLAB_BlenderCORTO_API(ui16Nposes,  ...
    strSceneData, ...
    strCameraData, ...
    strBlenderOpts, ...
    strReferenceData, ...
    bCALL_BLENDER, ...
    charPath2CORTO, ...
    charPath2BlenderExe, ...
    bRUN_IN_BACKGROUND, ...
    bVERBOSE_MODE)

arguments
    ui16Nposes          (1,1) uint16 {isscalar}
    strSceneData        (1,1) {isstruct}   
    strCameraData       (1,1) {isstruct} 
    strBlenderOpts      (1,1) {isstruct} 
    strReferenceData    (1,1) {isstruct}
    bCALL_BLENDER       (1,1) logical {islogical}
    charPath2CORTO      (1,:) 
    charPath2BlenderExe (1,:) 
    bRUN_IN_BACKGROUND  (1,1) logical {islogical} = true
    bVERBOSE_MODE       (1,1) logical {islogical} = false
end
% arguments
%     settings.bCALL_BLENDER
%     settings.bRUN_IN_BACKGROUND
%     settings.bVERBOSE_MODE
% end
%% PROTOTYPE
% [o_strConfigJSON, o_ui8ImgSequence, o_cOutputPath, o_strOutputFilesList] = MATLAB_BlenderCORTO_API(i_ui16Nposes,  ...
% SceneData, ...
% CameraData, ...
% BlenderOpts, ...
% ReferenceData, ...
% i_bCALL_BLENDER, ...
% i_cPath2CORTO, ...
% i_cPath2BlenderExe, ...
% i_bRUN_IN_BACKGROUND, ...
% i_bVERBOSE_MODE)
% -------------------------------------------------------------------------------------------------------------
%% DESCRIPTION
% What the function does
% -------------------------------------------------------------------------------------------------------------
%% INPUT
% ui16Nposes          (1,1) uint16 {isscalar}
% strSceneData        (1,1) {isstruct}
% strCameraData       (1,1) {isstruct}
% strBlenderOpts      (1,1) {isstruct}
% strReferenceData    (1,1) {isstruct}
% bCALL_BLENDER       (1,1) logical {islogical}
% charPath2CORTO      (1,:) string
% charPath2BlenderExe (1,:) string
% bRUN_IN_BACKGROUND  (1,1) logical {islogical} = true
% bVERBOSE_MODE       (1,1) logical {islogical} = false
% -------------------------------------------------------------------------------------------------------------
%% OUTPUT
% strConfigJSON
% ui8ImgSequence
% charOutputPath
% strOutputFilesList
% charInputConfigDataPath
% -------------------------------------------------------------------------------------------------------------
%% CHANGELOG
% 10-12-2023    Pietro Califano    First prototype coding. Call to Blender
%                                  verified and working correctly.
% 25-02-2024    Pietro Califano    Reworked interface using input structures
% 01-03-2024    Pietro Califano    Reworked version to use JSON interface of CORTO. Functioning version.
% 27-03-2024    Pietro Califano    Release version for Windows and Linux.
% -------------------------------------------------------------------------------------------------------------
%% DEPENDENCIES
% [-]
% -------------------------------------------------------------------------------------------------------------
%% Future upgrades
% MAJOR) Reworking as class object
% 1) Feature to handle assignment of two and more target bodies poses
% 6) Add error handling
% 7) Update for linux architectures (write bash instead of bat)
% 8) Add reference quantities saving in separate JSON file
% -------------------------------------------------------------------------------------------------------------
%% Function code

% COMMON TIMETAG
timetag = char(datetime('now', 'Format', 'yyyyMMdd_HH_mm'));

% Determine if system is Windows.
bIS_WINDOWS = strcmpi(computer, 'PCWIN64') || strcmpi(computer, 'PCWIN32');

if not(exist(charPath2CORTO, "var"))
    if bIS_WINDOWS == true
        charPath2CORTO = 'C:\devDir\corto_PeterCdev';
    else
        charPath2CORTO = '/home/peterc/devDir/corto_PeterCdev';
    end
    warning(strcat('CORTO repository path has not been specified. Assuming default: ', charPath2CORTO))
end

%% Input checks
% Check if required field exists, else throw error
strSceneDataRequired = ["rStateCam", "rTargetBody", "rSun", "qFromINtoCAM", "qFromINtoCAM", "scenarioName"];
strCameraDataRequired = ["fov", "resx", "resy"];
strBlenderOptional = ["encoding","rendSamples","viewSamples","scattering","filmexposure","viewtransform"];

checkFieldNames(strCameraData, strCameraDataRequired, true);
checkFieldNames(strSceneData, strSceneDataRequired, true);

% Handle cases for BlenderOpts
if isempty(fieldnames(strBlenderOpts))
    % Set default options for Blender rendering
    strBlenderOpts.encoding = 8;
    strBlenderOpts.rendSamples = 128;
    strBlenderOpts.viewSamples = 64;
    strBlenderOpts.scattering = 0;
    strBlenderOpts.filmexposure = 1;
    strBlenderOpts.viewtransform = 'Filmic';
else
    [~, ~, missingFields] = checkFieldNames(strBlenderOpts, strBlenderOptional, false);
    % scene_encoding = 8;
    % scene_rendSamples = 128;
    % scene_viewSamples = 64;
    % scene_scattering = 0;
    for idf = 1:length(missingFields)
        switch missingFields{idf}
            case "encoding"
                DEFAULT_VALUE = 8;
            case "rendSamples"
                DEFAULT_VALUE = 128;
            case "viewSamples"
                DEFAULT_VALUE = 64;
            case "scattering"
                DEFAULT_VALUE = 0;
            case "filmexposure"
                DEFAULT_VALUE = 1;
            case "viewtransform"
                DEFAULT_VALUE = 'Filmic';
        end
        strBlenderOpts.(missingFields{idf}) = DEFAULT_VALUE;
        disp(strcat("Field not found in BlenderOpts. Defaulting ", missingFields{idf}, " to value: ", num2str(DEFAULT_VALUE)));
    end
end

if not(isfield(strSceneData, 'labelDepth'))
    strSceneData.labelDepth = 0;
end
if not(isfield(strSceneData, 'labelSlopes'))
    strSceneData.labelSlopes = 0;
end
if not(isfield(strSceneData, 'labelID'))
    strSceneData.labelID = 0;
end

% Set default output path if not specified
if not(isfield(strBlenderOpts, 'savepath'))
    currentFolderPath = pwd;
    outputPath = strcat('CORTO_OUTPUT');

    if not(isfolder(fullfile(currentFolderPath, outputPath)))
        mkdir(outputPath);
    end

    strBlenderOpts.savepath = fullfile(currentFolderPath, outputPath);

    % Adjust path because... Windows
    if bIS_WINDOWS == true
        strBlenderOpts.savepath = strrep(strBlenderOpts.savepath, '\', '\\');
    end
end

% Optional flags
if nargin < 8
    bRUN_IN_BACKGROUND = true;
    bVERBOSE_MODE = false;
end

%% CONFIG FILE GENERATION
% Encapsulate data to CONFIG JSON
strConfigJSON.CameraData  = strCameraData;
strConfigJSON.BlenderOpts = strBlenderOpts;
strConfigJSON.SceneData   = strSceneData;

strConfigJSON = jsonencode(strConfigJSON, "PrettyPrint", true);
 
% Encapsulate data to REFERENCE JSON
if not(isempty( fieldnames(strReferenceData) ))
    strRefJSON.ReferenceData = strReferenceData;
    o_strRefJSON = jsonencode(strRefJSON, "PrettyPrint", true);
end

% Saves data to file
tmpFolderName = strcat("CORTO_INPUT");

% Create container folder if not existing
if not(isfolder(fullfile(tmpFolderName)))
    mkdir(tmpFolderName);
end
% Change to container folder
cd(tmpFolderName);

% Generate gitignore to avoid git detecting configuration files
fileID = fopen('.gitignore', 'w');
fprintf(fileID, '*.json\n*.bat');
fclose(fileID);

% Create time tagged folder
inputConfigFolder = strcat(strSceneData.scenarioName, '_inputConfigData_', timetag);
if isfolder(inputConfigFolder)
    warning('InputConfigData folder with same name detected. Overwriting...')
    rmdir(inputConfigFolder, 's')
end
mkdir(inputConfigFolder)
cd(inputConfigFolder)

charInputConfigDataPath = fullfile(tmpFolderName, inputConfigFolder);

% Saves data to CONFIG JSON
fileID = fopen('CORTO_CONFIG.json', 'w');
fprintf(fileID, strConfigJSON);
fclose(fileID);

% Saves data to REFERENCE JSON
if not(isempty( fieldnames(strReferenceData) ))
    fileID = fopen('CORTO_REFERENCE.json', 'w');
    fprintf(fileID, o_strRefJSON);
    fclose(fileID);
end

% Get absolute path to pass to CORTO
CORTO_CONFIG_ABSPATH = fullfile(which("CORTO_CONFIG.json"));
if bIS_WINDOWS == true
    CORTO_CONFIG_ABSPATH = strcat('"', CORTO_CONFIG_ABSPATH, '"'); % Handle the fact that Windows allows spaces in names...
end
cd('../..')

if not(exist("charPath2CORTO", 'var'))
    error("Path to CORTO directory not specified.")
end

charPath2CORTO = fullfile(charPath2CORTO);

if bIS_WINDOWS == true
    path2RenderFunction = fullfile(charPath2CORTO, "functions\\rendering\\RenderFromTxt.py"); % Default from repo structure
else
    path2RenderFunction = fullfile(charPath2CORTO, "functions/rendering/RenderFromTxt.py"); % Default from repo structure
end

if not(exist('i_bRUN_IN_BACKGROUND', 'var'))
    bRUN_IN_BACKGROUND = true;
end


% Inputs size checks
assert(ui16Nposes == size(strSceneData.rStateCam, 1), 'rStateCam rows must be equal to i_ui16Nposes.');
assert(ui16Nposes == size(strSceneData.rTargetBody, 1), 'rTargetBody rows must be equal to i_ui16Nposes.');
assert(ui16Nposes == size(strSceneData.rSun, 1), 'rSun rows must be equal to i_ui16Nposes.');
assert(ui16Nposes == size(strSceneData.qFromINtoCAM, 1), 'qFromCAMtoIN rows must be equal to i_ui16Nposes.');
assert(ui16Nposes == size(strSceneData.qFromINtoTF, 1), 'qFromTFtoIN rows must be equal to i_ui16Nposes.');

%% BLENDER CALL and IMAGE GENERATION
if bCALL_BLENDER == true

    if bIS_WINDOWS == true
        % FOR WINDOWS
        % Call to Blender if requested
        i_cBlenderFilePath = fullfile(charPath2CORTO, "data\scenarios\", strSceneData.scenarioName, "\", strcat(strSceneData.scenarioName, ".blend"));

        %     if not(exist(strcat(pwd, "\callBlenderWithCORTO.bat"), 'file'))
        batfileCode = cell(3, 1);
        % Write bat file to call Blender
        batfileCode{1} = "ECHO Calling Blender with CORTO to generate images sequence...";

        if not(exist('i_cBlenderPath', 'var'))
            % Requires Blender in Systems paths (Environment variables on Windows)
            batfileCode{2} = "blender " + i_cBlenderFilePath;
        else
            batfileCode{2} = charPath2BlenderExe + "blender" + " " + i_cBlenderFilePath;
            % Needed because python script cannot be executed directly due to bpy but must be called by Blender
        end

        if bRUN_IN_BACKGROUND == true
            batfileCode{2} = batfileCode{2} + " --background";
        end

        % ADD PYTHON SCRIPT CALL
        batfileCode{3} = "--python " + path2RenderFunction + " --";

        % Add verbose flag if requested
        if bVERBOSE_MODE == true
            batfileCode{3} = batfileCode{3} + " -v";
        end

        % Attach configuration option and path
        batfileCode{3} = batfileCode{3} + " -c " + CORTO_CONFIG_ABSPATH;

        fileTowrite = fopen(strcat(fullfile(tmpFolderName, inputConfigFolder), '\callBlenderWithCORTO.bat'), 'w');
        fprintf(fileTowrite,'%s \n', batfileCode{1});

        for rowid = 2:length(batfileCode)
            fprintf(fileTowrite,'%s ', batfileCode{rowid});
        end
        fclose(fileTowrite);
        % CALL BAT FILE
        system(strcat(fullfile(tmpFolderName, inputConfigFolder), '\callBlenderWithCORTO.bat'));

    else
        % FOR LINUX
        % Call to Blender if requested
        i_cBlenderFilePath = fullfile(charPath2CORTO, "data/scenarios", strSceneData.scenarioName, strcat(strSceneData.scenarioName, ".blend"));
                   
        % Compose command
        commandString = "blender " + i_cBlenderFilePath;

        if bRUN_IN_BACKGROUND == true
            commandString = strcat(commandString, " --background");
        end

        % ADD PYTHON SCRIPT CALL
        commandString = strcat(commandString, " --python " + path2RenderFunction + " --");

        % Add verbose flag if requested
        if bVERBOSE_MODE == true
            commandString = strcat(commandString, " -v");
        end

        % Attach configuration option and path
        % ACHTUNG: REQUIRED TO MAKE SURE BLENDER USES SYSTEM-LIB
        ldconfigString = 'export LD_LIBRARY_PATH=/lib/x86_64-linux-gnu'; 
        commandString = strcat(commandString, " -c ", CORTO_CONFIG_ABSPATH);

        % Create bash script file to save the command
        fileTowrite = fopen(fullfile(tmpFolderName, inputConfigFolder, 'callBlenderWithCORTO.sh'), 'w');
        fprintf(fileTowrite,'%s\n%s\n', ldconfigString, commandString);
        fclose(fileTowrite);

        % RENDER CALL
        bashScriptPath = strcat(fullfile(tmpFolderName, inputConfigFolder), '/callBlenderWithCORTO.sh');
        fileattrib(bashScriptPath, '+x'); % Make script executable
        unix(bashScriptPath, '-echo')
    end

    %% OUTPUT READING AND ASSIGNMENT 

    % Get output folder info
    outDirStruct = dir(strBlenderOpts.savepath);

    % Remove useless directories
    removeEntryMask = false(length(outDirStruct) ,1);

    for idF = 1:length(outDirStruct)      
        if strcmpi(outDirStruct(idF).name, '.') || strcmpi(outDirStruct(idF).name, '..')
            removeEntryMask(idF) = true;
        end
    end

    outDirStruct(removeEntryMask) = [];

    if not(isfield(strBlenderOpts, "redirect_output")) || strBlenderOpts.redirect_output == false
        % Get ID of newest folder (max datenum)
        maxID = 1;
        maxDatenum = 0;

        for idF = 1:length(outDirStruct)
            % tmpMax = convertTo(dirStruct.date, "posixtime");
            if outDirStruct(idF).datenum > maxDatenum
                maxDatenum = outDirStruct(idF).datenum;
                maxID = idF;
            end
        end

        % Assembly output path
        charOutputPath = fullfile(outDirStruct(maxID).folder, outDirStruct(maxID).name);

        if bIS_WINDOWS == true
            charOutputPath = fullfile(charOutputPath, '\\img');
        else
            charOutputPath = fullfile(charOutputPath, '/img');
        end

    elseif isfield(strBlenderOpts, "redirect_output") && strBlenderOpts.redirect_output == true
        charOutputPath = fullfile(strBlenderOpts.savepath, "images");
    end

    try
        % Get png file list in output directory
        strOutputFilesList = dir(fullfile(charOutputPath, "*.png"));

        % Read sample image for allocation
        imgSample = imread(fullfile(strOutputFilesList(1).folder, strOutputFilesList(1).name));
        % Get size of image
        [xSize, ySize] = size(imgSample);
        % Allocate
        ui8ImgSequence = zeros(xSize, ySize, length(strOutputFilesList), class(imgSample));

        % READ images sequentially one-by-one
        for idI = 1:length(strOutputFilesList)

            img = imread(fullfile(strOutputFilesList(idI).folder, strOutputFilesList(idI).name));

            % Cast to integer array if not
            if not(isinteger(img))
                try
                    img = uint8(img);
                catch
                    error('Unable to convert image array to uint8 type.');
                end
            end

            % Allocate image in sequence
            ui8ImgSequence(:, :, idI) = img;
        end
    catch
        warning('Output images not found: unable to load. Check output path!')
        ui8ImgSequence = [];
        charOutputPath = "";
        strOutputFilesList = struct();
        charInputConfigDataPath = "";
    end

else
    % Return placeholder values
    ui8ImgSequence = uint16(-1);
    charOutputPath = '';
end

end

%% LOCAL FUNCTION
% Function checking field names in configuration structures
function [checkFlag, errMsg, missingFields] = checkFieldNames(inputStruct, requiredFields, bThrowErrorIfAny)

checkFlag = true; % Default: ALL OK
missingFields = cell(1);
idC = 1;

% Check if all required fields have been defined in struct()
for idf = 1:length(requiredFields)

    if not(isfield(inputStruct, requiredFields(idf)))
        checkFlag = false;
        missingFields{idC} = requiredFields(idf); 
        idC = idC + 1;
    end

end

errMsg = 'Input structure has missing fields!';

if bThrowErrorIfAny && not(checkFlag)
    error(errMsg);
end

end
