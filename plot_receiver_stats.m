function plot_receiver_stats(a, Tlim, maxRate, maxDelay, U)
    % Plot receiver statistics from parsed data
    %
    % Usage:
    %   a = load('parsed_stats.txt');
    %   plot_receiver_stats(a, [0 100], 50, 0.1, 10);
    %
    % Parameters:
    %   a       - Data matrix from parse_receiver_stats
    %   Tlim    - Time range [min max] in seconds, e.g., [0 100]
    %   maxRate - Max receive rate for y-axis [Mbps]
    %   maxDelay - Max delay for y-axis [s]
    %   U       - Window size for moving average filter
    %
    % Data columns:
    %   1: Time (s)
    %   2: Datagrams received
    %   3: Bytes received
    %   4: Receive rate (Mbps)
    %   5: Frames completed
    %   6: Total frames rendered
    %   7: Freeze count
    %   8: Total freeze duration (s)
    %   9: Total Inter-Frame Delay (s)
    %   10: Inter-Frame Delay Variance (s^2)

    % Time vector (normalize to start at 0)
    T = a(:,1);
    T = T - T(1);

    % Moving average filter
    B = ones(1, U) / U;

    % Create figure with 4 subplots
    figure('Position', [100, 100, 800, 900]);
    K = 4;  % Number of subplots
    L = 1;  % Current subplot index

    %% Subplot 1: Receive Rate and Frames Completed
    subplot(K, 1, L); L = L + 1;
    
    yyaxis left;
    plot(T, filter(B, 1, a(:,4)), 'b-', 'LineWidth', 1.5);
    ylabel('Receive Rate [Mbps]');
    ylim([0 maxRate]);
    
    yyaxis right;
    plot(T, a(:,5), 'r-', 'LineWidth', 1.5);
    ylabel('Frames Completed');
    
    set(gca, 'FontSize', 12);
    grid on;
    title('Receive Rate and Frames Completed per Interval');
    legend('Receive Rate', 'Frames Completed', 'Location', 'best');
    set(gca, 'XTickLabel', []);
    xlim(Tlim);

    %% Subplot 2: Total Frames Rendered (cumulative)
    subplot(K, 1, L); L = L + 1;
    
    plot(T, a(:,6), 'g-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 12);
    grid on;
    title('Total Frames Rendered (Cumulative)');
    ylabel('Frames');
    set(gca, 'XTickLabel', []);
    xlim(Tlim);

    %% Subplot 3: Freeze Count and Freeze Duration
    subplot(K, 1, L); L = L + 1;
    
    yyaxis left;
    plot(T, a(:,7), 'b-', 'LineWidth', 1.5);
    ylabel('Freeze Count');
    
    yyaxis right;
    plot(T, a(:,8), 'r-', 'LineWidth', 1.5);
    ylabel('Freeze Duration [s]');
    
    set(gca, 'FontSize', 12);
    grid on;
    title('Freeze Count and Total Freeze Duration');
    legend('Freeze Count', 'Freeze Duration', 'Location', 'best');
    set(gca, 'XTickLabel', []);
    xlim(Tlim);

    %% Subplot 4: Inter-Frame Delay and Variance
    subplot(K, 1, L); L = L + 1;
    
    yyaxis left;
    plot(T, a(:,9), 'b-', 'LineWidth', 1.5);
    ylabel('Inter-Frame Delay [s]');
    ylim([0 maxDelay * 100]);  % Scale appropriately
    
    yyaxis right;
    plot(T, a(:,10) * 1e6, 'r-', 'LineWidth', 1.5);  % Convert to microseconds^2
    ylabel('Delay Variance [μs^2]');
    
    set(gca, 'FontSize', 12);
    grid on;
    title('Total Inter-Frame Delay and Delay Variance');
    legend('Inter-Frame Delay', 'Delay Variance', 'Location', 'best');
    xlim(Tlim);
    xlabel('Time [s]');

end