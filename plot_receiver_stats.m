function plot_receiver_stats_vertical(a, Tlim, maxRate, maxDelay, U)
    % Plot receiver statistics - each metric in its own subplot (vertical layout)
    %
    % Usage:
    %   a = load('parsed_stats.txt');
    %   plot_receiver_stats_vertical(a, [0 100], 50, 0.1, 10);

    % Time vector (normalize to start at 0)
    T = a(:,1);
    T = T - T(1);

    % Moving average filter
    B = ones(1, U) / U;

    % Create tall figure with 8 subplots
    figure('Position', [100, 50, 800, 1200]);
    K = 8;  % Number of subplots
    L = 1;  % Current subplot index

    %% Subplot 1: Receive Rate
    subplot(K, 1, L); L = L + 1;
    plot(T, filter(B, 1, a(:,4)), 'b-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 10);
    grid on;
    title('Receive Rate');
    ylabel('[Mbps]');
    ylim([0 maxRate]);
    xlim(Tlim);
    set(gca, 'XTickLabel', []);

    %% Subplot 2: Datagrams Received
    subplot(K, 1, L); L = L + 1;
    plot(T, a(:,2), 'm-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 10);
    grid on;
    title('Datagrams Received per Interval');
    ylabel('Count');
    xlim(Tlim);
    set(gca, 'XTickLabel', []);

    %% Subplot 3: Frames Completed per Interval
    subplot(K, 1, L); L = L + 1;
    plot(T, a(:,5), 'r-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 10);
    grid on;
    title('Frames Completed per Interval');
    ylabel('Frames');
    xlim(Tlim);
    set(gca, 'XTickLabel', []);

    %% Subplot 4: Total Frames Rendered
    subplot(K, 1, L); L = L + 1;
    plot(T, a(:,6), 'g-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 10);
    grid on;
    title('Total Frames Rendered (Cumulative)');
    ylabel('Frames');
    xlim(Tlim);
    set(gca, 'XTickLabel', []);

    %% Subplot 5: Freeze Count
    subplot(K, 1, L); L = L + 1;
    plot(T, a(:,7), 'b-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 10);
    grid on;
    title('Freeze Count (Cumulative)');
    ylabel('Count');
    xlim(Tlim);
    set(gca, 'XTickLabel', []);

    %% Subplot 6: Total Freeze Duration
    subplot(K, 1, L); L = L + 1;
    plot(T, a(:,8), 'r-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 10);
    grid on;
    title('Total Freeze Duration (Cumulative)');
    ylabel('[s]');
    xlim(Tlim);
    set(gca, 'XTickLabel', []);

    %% Subplot 7: Total Inter-Frame Delay
    subplot(K, 1, L); L = L + 1;
    plot(T, a(:,9), 'b-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 10);
    grid on;
    title('Total Inter-Frame Delay (Cumulative)');
    ylabel('[s]');
    ylim([0 maxDelay * 100]);
    xlim(Tlim);
    set(gca, 'XTickLabel', []);

    %% Subplot 8: Inter-Frame Delay Variance
    subplot(K, 1, L); L = L + 1;
    plot(T, a(:,10) * 1e6, 'r-', 'LineWidth', 1.5);
    set(gca, 'FontSize', 10);
    grid on;
    title('Inter-Frame Delay Variance');
    ylabel('[us^2]');
    xlim(Tlim);
    xlabel('Time [s]');

end