function data = parse_receiver_log(input_file, output_file)
    % Parse receiver statistics from log file
    % Usage:
    %   data = parse_receiver_log('receiver_log.txt', 'parsed_stats.txt');
    %
    % Input log format:
    %   === RECEIVER STATS (last 1.00031s) ===
    %   Datagrams received: 1233
    %   Bytes received: 1476533
    %   Receive rate: 11.8087 Mbps
    %   Frames completed: 29
    %   Total frames rendered: 239
    %   Freeze count: 0, total freeze duration: 0 s
    %   Total Inter-Frame Delay: 7.96977 s
    %   Inter-Frame Delay Variance: 2.74551e-05 s^2
    %   =================================================
    %
    % Output columns:
    %   1: Time (cumulative seconds)
    %   2: Datagrams received
    %   3: Bytes received
    %   4: Receive rate (Mbps)
    %   5: Frames completed
    %   6: Total frames rendered
    %   7: Freeze count
    %   8: Total freeze duration (s)
    %   9: Total Inter-Frame Delay (s)
    %   10: Inter-Frame Delay Variance (s^2)

    fid = fopen(input_file, 'r');
    if fid == -1
        error('Cannot open input file: %s', input_file);
    end

    % Initialize storage
    data = [];
    cumulative_time = 0;
    
    % Temporary storage for current record
    current_record = zeros(1, 10);
    interval_time = 1.0;  % default interval

    while ~feof(fid)
        line = fgetl(fid);
        if ~ischar(line)
            break;
        end

        % Parse each line type
        if ~isempty(strfind(line, '=== RECEIVER STATS'))
            % Extract interval time from header
            tokens = regexp(line, 'last ([0-9.]+)s', 'tokens');
            if ~isempty(tokens)
                interval_time = str2double(tokens{1}{1});
            end
            current_record = zeros(1, 10);
            
        elseif ~isempty(strfind(line, 'Datagrams received:'))
            tokens = regexp(line, 'Datagrams received: ([0-9]+)', 'tokens');
            if ~isempty(tokens)
                current_record(2) = str2double(tokens{1}{1});
            end
            
        elseif ~isempty(strfind(line, 'Bytes received:'))
            tokens = regexp(line, 'Bytes received: ([0-9]+)', 'tokens');
            if ~isempty(tokens)
                current_record(3) = str2double(tokens{1}{1});
            end
            
        elseif ~isempty(strfind(line, 'Receive rate:'))
            tokens = regexp(line, 'Receive rate: ([0-9.e+-]+)', 'tokens');
            if ~isempty(tokens)
                current_record(4) = str2double(tokens{1}{1});
            end
            
        elseif ~isempty(strfind(line, 'Frames completed:'))
            tokens = regexp(line, 'Frames completed: ([0-9]+)', 'tokens');
            if ~isempty(tokens)
                current_record(5) = str2double(tokens{1}{1});
            end
            
        elseif ~isempty(strfind(line, 'Total frames rendered:'))
            tokens = regexp(line, 'Total frames rendered: ([0-9]+)', 'tokens');
            if ~isempty(tokens)
                current_record(6) = str2double(tokens{1}{1});
            end
            
        elseif ~isempty(strfind(line, 'Freeze count:'))
            tokens = regexp(line, 'Freeze count: ([0-9]+), total freeze duration: ([0-9.e+-]+)', 'tokens');
            if ~isempty(tokens)
                current_record(7) = str2double(tokens{1}{1});
                current_record(8) = str2double(tokens{1}{2});
            end
            
        elseif ~isempty(strfind(line, 'Total Inter-Frame Delay:'))
            tokens = regexp(line, 'Total Inter-Frame Delay: ([0-9.e+-]+)', 'tokens');
            if ~isempty(tokens)
                current_record(9) = str2double(tokens{1}{1});
            end
            
        elseif ~isempty(strfind(line, 'Inter-Frame Delay Variance:'))
            tokens = regexp(line, 'Inter-Frame Delay Variance: ([0-9.e+-]+)', 'tokens');
            if ~isempty(tokens)
                current_record(10) = str2double(tokens{1}{1});
            end
            
        elseif ~isempty(strfind(line, '=====')) && length(line) > 10
            % End of record - save it
            cumulative_time = cumulative_time + interval_time;
            current_record(1) = cumulative_time;
            data = [data; current_record];
        end
    end

    fclose(fid);

    % Save to output file if specified
    if nargin >= 2 && ~isempty(output_file)
        save(output_file, 'data', '-ascii', '-double');
        fprintf('Parsed %d records, saved to %s\n', size(data, 1), output_file);
    end

    fprintf('Parsed %d statistical records\n', size(data, 1));
end