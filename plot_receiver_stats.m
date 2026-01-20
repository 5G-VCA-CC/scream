function plot_receiver_stats_separate(a, Tlim, maxRate, maxDelay, U)
    % Plot receiver statistics - Each statistic in its own subplot
    %
    % Usage:
    %   a = load('parsed_stats.txt');
    %   plot_receiver_stats_separate(a, [0 100], 50, 0.1, 10);

    % Time vector (normalize to start at 0)
    T = a(:,1);
    if ~isempty(T)
        T = T - T(1);
    end

    % Moving average filter
    B = ones(1, U) / U;

    % Create a tall figure to accommodate 7 plots
    % [left bottom width height]
    figure('Position', [100, 50, 800, 1200]); 
    
    K = 7; % Total number of subplots
    L = 1; % Current subplot counter

    %% 1. Receive Rate
    subplot(K, 1, L); L = L + 1;
    plot(T, filter(B, 1, a(:,4)), 'b-', 'LineWidth', 1.5);
    ylabel('Rate [Mbps]');
    ylim([0 maxRate]);
    xlim(Tlim);
    set(gca, 'FontSize', 10, 'XTickLabel', []);
    grid on;
    title('1. Receive Rate');

    %% 2. Frames Completed (Per Interval)
    subplot(K, 1, L); L = L + 1;
    plot(T, a(:,5), 'r-', 'LineWidth', 1.5);
    ylabel('Count');
    xlim(Tlim);
    set(gca, 'FontSize', 10, 'XTickLabel', []);
    grid on;
    title('2. Frames Completed (Per Interval)');

    %% 3. Total Frames Rendered (Cumulative)
    subplot(K, 1, L); L = L + 1;
    plot(T, a(:,6), 'g-', 'LineWidth', 1.5);
    ylabel('Frames');
    xlim(Tlim);
    set(gca, 'FontSize', 10, 'XTickLabel', []);
    grid on;
    title('3. Total Frames Rendered');

    %% 4. Freeze Count
    subplot(K, 1, L); L = L + 1;
    plot(T, a(:,7), 'k-', 'LineWidth', 1.5);
    ylabel('Count');
    xlim(Tlim);
    set(gca, 'FontSize', 10, 'XTickLabel', []);
    grid on;
    title('4. Freeze Count');

    %% 5. Freeze Duration
    subplot(K, 1, L); L = L + 1;
    plot(T, a(:,8), 'm-', 'LineWidth', 1.5);
    ylabel('Duration [s]');
    xlim(Tlim);
    set(gca, 'FontSize', 10, 'XTickLabel', []);
    grid on;
    title('5. Total Freeze Duration');

    %% 6. Total Inter-Frame Delay
    subplot(K, 1, L); L = L + 1;
    plot(T, a(:,9), 'b-', 'LineWidth', 1.5);
    ylabel('Delay [s]');
    % Note: Since this is "Total" (accumulated), standard scaling might cut it off.
    % Using maxDelay*100 as per previous logic, or you can comment it out to autoscale.
    ylim([0 maxDelay * 100]); 
    xlim(Tlim);
    set(gca, 'FontSize', 10, 'XTickLabel', []);
    grid on;
    title('6. Total Inter-Frame Delay');

    %% 7. Inter-Frame Delay Variance
    subplot(K, 1, L); L = L + 1;
    % Convert to microseconds for better readability
    plot(T, a(:,10) * 1e6, 'r-', 'LineWidth', 1.5); 
    ylabel('Var [\mus^2]');
    xlim(Tlim);
    set(gca, 'FontSize', 10); % Keep X labels for the bottom plot
    grid on;
    title('7. Delay Variance');
    xlabel('Time [s]');

end