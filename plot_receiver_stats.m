function plot_receiver_stats_separate(a, Tlim, maxRate, maxDelay, U)
    % Plot receiver statistics with each metric in its own subplot
    %
    % Usage:
    %   a = load('parsed_stats.txt');
    %   plot_receiver_stats_separate(a, [0 100], 50, 0.1, 10);

    % Time vector (normalize to start at 0)
    T = a(:,1);
    T = T - T(1);

    % Moving average filter
    B = ones(1, U) / U;

    % Debug: Print variance range to check values
    fprintf('Variance range: min=%e, max=%e\n', min(a(:,10)), max(a(:,10)));
    fprintf('Variance * 1e6 range: min=%e, max=%e\n', min(a(:,10)*1e6), max(a(:,10)*1e6));

    % Create figure with 8 subplots (2 columns x 4 rows)
    figure('Position', [100, 50, 1200, 900]);
    
    %% Subplot 1: Receive Rate
    subplot(4, 2, 1);
    plot(T, filter(B, 1, a(:,4)), 'b-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 11);
    grid on;
    title('Receive Rate');
    ylabel('Rate [Mbps]');
    ylim([0 maxRate]);
    xlim(Tlim);
    set(gca, 'XTickLabel', []);

    %% Subplot 2: Datagrams Received
    subplot(4, 2, 2);
    plot(T, a(:,2), 'm-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 11);
    grid on;
    title('Datagrams Received per Interval');
    ylabel('Datagrams');
    xlim(Tlim);
    set(gca, 'XTickLabel', []);

    %% Subplot 3: Frames Completed per Interval
    subplot(4, 2, 3);
    plot(T, a(:,5), 'r-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 11);
    grid on;
    title('Frames Completed per Interval');
    ylabel('Frames');
    xlim(Tlim);
    set(gca, 'XTickLabel', []);

    %% Subplot 4: Total Frames Rendered (cumulative)
    subplot(4, 2, 4);
    plot(T, a(:,6), 'g-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 11);
    grid on;
    title('Total Frames Rendered (Cumulative)');
    ylabel('Frames');
    xlim(Tlim);
    set(gca, 'XTickLabel', []);

    %% Subplot 5: Freeze Count
    subplot(4, 2, 5);
    plot(T, a(:,7), 'b-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 11);
    grid on;
    title('Freeze Count (Cumulative)');
    ylabel('Count');
    xlim(Tlim);
    set(gca, 'XTickLabel', []);

    %% Subplot 6: Total Freeze Duration
    subplot(4, 2, 6);
    plot(T, a(:,8), 'r-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 11);
    grid on;
    title('Total Freeze Duration (Cumulative)');
    ylabel('Duration [s]');
    xlim(Tlim);
    set(gca, 'XTickLabel', []);

    %% Subplot 7: Total Inter-Frame Delay
    subplot(4, 2, 7);
    plot(T, a(:,9), 'b-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 11);
    grid on;
    title('Total Inter-Frame Delay (Cumulative)');
    ylabel('Delay [s]');
    xlim(Tlim);
    xlabel('Time [s]');

    %% Subplot 8: Inter-Frame Delay Variance (FIXED)
    subplot(4, 2, 8);
    
    % Get variance data
    variance_data = a(:,10);
    
    % Check if data exists and is non-zero
    if all(variance_data == 0)
        text(0.5, 0.5, 'No variance data (all zeros)', ...
             'HorizontalAlignment', 'center', 'Units', 'normalized');
    else
        % Scale appropriately based on magnitude
        max_var = max(variance_data);
        
        if max_var < 1e-9
            % Very small: use nanoseconds squared
            plot(T, variance_data * 1e18, 'r-', 'LineWidth', 1.5);
            ylabel('Variance [ns^2]');
        elseif max_var < 1e-6
            % Small: use microseconds squared
            plot(T, variance_data * 1e12, 'r-', 'LineWidth', 1.5);
            ylabel('Variance [us^2]');
        elseif max_var < 1e-3
            % Medium: use milliseconds squared
            plot(T, variance_data * 1e6, 'r-', 'LineWidth', 1.5);
            ylabel('Variance [ms^2]');
        else
            % Large: keep in seconds squared
            plot(T, variance_data, 'r-', 'LineWidth', 1.5);
            ylabel('Variance [s^2]');
        end
        
        % Set reasonable y-axis limits
        ylim([0 max(variance_data * 1.1) * get_scale_factor(max_var)]);
    end
    
    set(gca, 'FontSize', 11);
    grid on;
    title('Inter-Frame Delay Variance');
    xlim(Tlim);
    xlabel('Time [s]');

end

% Helper function to get scale factor
function sf = get_scale_factor(max_var)
    if max_var < 1e-9
        sf = 1e18;
    elseif max_var < 1e-6
        sf = 1e12;
    elseif max_var < 1e-3
        sf = 1e6;
    else
        sf = 1;
    end
end