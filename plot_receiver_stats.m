function plot_receiver_stats_dual(a, Tlim, maxRate, maxDelay, U)
    % Plot receiver statistics with dual y-axes
    % Usage:
    %   a = load('parsed_stats.txt');
    %   plot_receiver_stats_dual(a, [0 100], 50, 0.1, 10);

    % Time vector (normalize to start at 0)
    T = a(:,1);
    T = T - T(1);

    % Moving average filter
    B = ones(1, U) / U;

    % Create figure with 4 subplots
    figure('Position', [100, 100, 800, 900]);
    K = 4;
    L = 1;

    %% Subplot 1: Receive Rate and Frames Completed
    subplot(K, 1, L); L = L + 1;
    [ax, h1, h2] = plotyy(T, filter(B, 1, a(:,4)), T, a(:,5));
    
    set(h1, 'Color', 'b', 'LineWidth', 1.5);
    set(h2, 'Color', 'r', 'LineWidth', 1.5);
    set(ax(1), 'YColor', 'b');
    set(ax(2), 'YColor', 'r');
    
    ylabel(ax(1), 'Receive Rate [Mbps]');
    ylabel(ax(2), 'Frames Completed');
    set(ax(1), 'YLim', [0 maxRate]);
    set(ax(1), 'XLim', Tlim);
    set(ax(2), 'XLim', Tlim);
    
    set(gca, 'FontSize', 12);
    grid on;
    title('Receive Rate and Frames Completed per Interval');
    legend([h1; h2], 'Receive Rate', 'Frames Completed', 'Location', 'best');
    set(ax(1), 'XTickLabel', []);
    set(ax(2), 'XTickLabel', []);

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
    [ax, h1, h2] = plotyy(T, a(:,7), T, a(:,8));
    
    set(h1, 'Color', 'b', 'LineWidth', 1.5);
    set(h2, 'Color', 'r', 'LineWidth', 1.5);
    set(ax(1), 'YColor', 'b');
    set(ax(2), 'YColor', 'r');
    
    ylabel(ax(1), 'Freeze Count');
    ylabel(ax(2), 'Freeze Duration [s]');
    set(ax(1), 'XLim', Tlim);
    set(ax(2), 'XLim', Tlim);
    
    set(gca, 'FontSize', 12);
    grid on;
    title('Freeze Count and Total Freeze Duration');
    legend([h1; h2], 'Freeze Count', 'Freeze Duration', 'Location', 'best');
    set(ax(1), 'XTickLabel', []);
    set(ax(2), 'XTickLabel', []);

    %% Subplot 4: Inter-Frame Delay and Variance
    subplot(K, 1, L); L = L + 1;
    [ax, h1, h2] = plotyy(T, a(:,9), T, a(:,10) * 1e6);
    
    set(h1, 'Color', 'b', 'LineWidth', 1.5);
    set(h2, 'Color', 'r', 'LineWidth', 1.5);
    set(ax(1), 'YColor', 'b');
    set(ax(2), 'YColor', 'r');
    
    ylabel(ax(1), 'Inter-Frame Delay [s]');
    ylabel(ax(2), 'Delay Variance [us^2]');
    set(ax(1), 'YLim', [0 maxDelay * 100]);
    set(ax(1), 'XLim', Tlim);
    set(ax(2), 'XLim', Tlim);
    
    set(gca, 'FontSize', 12);
    grid on;
    title('Total Inter-Frame Delay and Delay Variance');
    legend([h1; h2], 'Inter-Frame Delay', 'Delay Variance', 'Location', 'best');
    xlabel('Time [s]');

end