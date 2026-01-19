function a = import_receiver_log(filename)
% Reads the specific SCReAM receiver text log and converts to matrix
% Returns matrix 'a' with columns:
% 1: Time (Accumulated seconds)
% 2: Receive Rate (Mbps)
% 3: Frames Completed
% 4: Freeze Count
% 5: Freeze Duration (s)
% 6: Total Inter-Frame Delay (s)
% 7: Inter-Frame Delay Variance (s^2)

    fid = fopen(filename, 'r');
    if fid == -1
        error('Cannot open file');
    end

    data = [];
    current_time = 0;
    
    % Temporary storage for the current block
    rate = 0; frames = 0; f_cnt = 0; f_dur = 0; delay = 0; var = 0;
    time_increment = 1.0; % Default if parsing fails

    while ~feof(fid)
        line = fgetl(fid);
        
        % 1. Detect Header to get time increment
        if contains(line, 'RECEIVER STATS')
            % Extract "1.00031" from "last 1.00031s"
            t_str = regexp(line, 'last ([\d\.]+)s', 'tokens');
            if ~isempty(t_str)
                time_increment = str2double(t_str{1}{1});
            end
            current_time = current_time + time_increment;
        end

        % 2. Extract Receive Rate
        if contains(line, 'Receive rate:')
            tokens = regexp(line, 'Receive rate: ([\d\.]+) Mbps', 'tokens');
            if ~isempty(tokens), rate = str2double(tokens{1}{1}); end
        end

        % 3. Extract Frames Completed
        if contains(line, 'Frames completed:')
            tokens = regexp(line, 'Frames completed: (\d+)', 'tokens');
            if ~isempty(tokens), frames = str2double(tokens{1}{1}); end
        end

        % 4. Extract Freeze Count and Duration
        if contains(line, 'Freeze count:')
            % Pattern: Freeze count: 0, total freeze duration: 0 s
            tokens = regexp(line, 'Freeze count: (\d+), total freeze duration: ([\d\.]+) s', 'tokens');
            if ~isempty(tokens)
                f_cnt = str2double(tokens{1}{1});
                f_dur = str2double(tokens{1}{2});
            end
        end

        % 5. Extract Total Inter-Frame Delay
        if contains(line, 'Total Inter-Frame Delay:')
            tokens = regexp(line, 'Total Inter-Frame Delay: ([\d\.]+) s', 'tokens');
            if ~isempty(tokens), delay = str2double(tokens{1}{1}); end
        end

        % 6. Extract Variance and Save Row
        if contains(line, 'Inter-Frame Delay Variance:')
            tokens = regexp(line, 'Inter-Frame Delay Variance: ([\d\.eE\-\+]+) s\^2', 'tokens');
            if ~isempty(tokens)
                var = str2double(tokens{1}{1});
                
                % End of block, append to matrix
                new_row = [current_time, rate, frames, f_cnt, f_dur, delay, var];
                data = [data; new_row];
            end
        end
    end
    fclose(fid);
    a = data;
end