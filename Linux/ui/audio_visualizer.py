"""
Audio Visualizer Widget
Real-time audio level visualization using GTK DrawingArea
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Graphene
import cairo
import math
from typing import List
from collections import deque


class AudioVisualizer(Gtk.DrawingArea):
    """
    Real-time audio level visualizer with smooth bar animation
    """
    
    NUM_BARS = 12
    BAR_SPACING = 4
    CORNER_RADIUS = 4
    ANIMATION_SPEED = 0.15  # Smoothing factor
    
    # Color gradient (blue theme)
    LOW_COLOR = (0.23, 0.51, 0.96)    # #3b82f6
    HIGH_COLOR = (0.38, 0.65, 0.98)   # #60a5fa
    PEAK_COLOR = (0.94, 0.27, 0.27)   # #ef4444
    
    def __init__(self):
        super().__init__()
        
        self.add_css_class('visualizer')
        self.set_size_request(-1, 60)
        self.set_hexpand(True)
        
        # Current and target levels for each bar
        self._current_levels: List[float] = [0.0] * self.NUM_BARS
        self._target_levels: List[float] = [0.0] * self.NUM_BARS
        
        # Level history for smooth visualization
        self._level_history: deque = deque(maxlen=self.NUM_BARS)
        
        # Animation state
        self._is_active = False
        self._animation_id: int = 0
        
        # Set up drawing
        self.set_draw_func(self._draw)
        
    def set_level(self, level: float):
        """
        Set the current audio level (0.0 to 1.0)
        This creates a visualization effect by distributing the level across bars
        """
        level = max(0.0, min(1.0, level))
        
        # Add to history
        self._level_history.append(level)
        
        # Calculate target levels for each bar based on history
        history_list = list(self._level_history)
        for i in range(self.NUM_BARS):
            if i < len(history_list):
                # Use historical values with some variation
                base = history_list[-(i + 1)] if (i + 1) <= len(history_list) else 0
                # Add slight variation for visual interest
                variation = math.sin(i * 0.5 + level * 10) * 0.1
                self._target_levels[i] = max(0.0, min(1.0, base + variation))
            else:
                self._target_levels[i] = level * (1 - i / self.NUM_BARS)
                
        # Start animation if not running
        if not self._is_active:
            self._start_animation()
            
    def _start_animation(self):
        """Start the animation loop"""
        if self._animation_id:
            return
            
        self._is_active = True
        self._animation_id = GLib.timeout_add(16, self._animate)  # ~60fps
        
    def _stop_animation(self):
        """Stop the animation loop"""
        if self._animation_id:
            GLib.source_remove(self._animation_id)
            self._animation_id = 0
        self._is_active = False
        
    def _animate(self) -> bool:
        """Animation tick - smooth transitions"""
        any_change = False
        
        for i in range(self.NUM_BARS):
            diff = self._target_levels[i] - self._current_levels[i]
            if abs(diff) > 0.001:
                # Smooth transition
                self._current_levels[i] += diff * self.ANIMATION_SPEED
                any_change = True
            else:
                self._current_levels[i] = self._target_levels[i]
                
        self.queue_draw()
        
        # Keep animating while there are changes or level is above 0
        if not any_change and all(l < 0.01 for l in self._current_levels):
            self._is_active = False
            self._animation_id = 0
            return False
            
        return True
        
    def _draw(self, area, cr, width, height):
        """Draw the visualization"""
        # Calculate bar dimensions
        total_spacing = (self.NUM_BARS - 1) * self.BAR_SPACING
        bar_width = (width - total_spacing) / self.NUM_BARS
        max_height = height - 8  # Padding
        
        # Draw each bar
        for i in range(self.NUM_BARS):
            x = i * (bar_width + self.BAR_SPACING)
            level = self._current_levels[i]
            bar_height = max(4, level * max_height)  # Minimum height
            y = height - 4 - bar_height
            
            # Gradient color based on level
            if level > 0.9:
                r, g, b = self.PEAK_COLOR
            else:
                # Interpolate between low and high color
                t = level
                r = self.LOW_COLOR[0] + (self.HIGH_COLOR[0] - self.LOW_COLOR[0]) * t
                g = self.LOW_COLOR[1] + (self.HIGH_COLOR[1] - self.LOW_COLOR[1]) * t
                b = self.LOW_COLOR[2] + (self.HIGH_COLOR[2] - self.LOW_COLOR[2]) * t
                
            # Draw rounded rectangle
            self._draw_rounded_rect(cr, x, y, bar_width, bar_height, self.CORNER_RADIUS)
            
            # Create gradient
            pattern = cairo.LinearGradient(x, y, x, y + bar_height)
            pattern.add_color_stop_rgb(0, min(1, r * 1.3), min(1, g * 1.3), min(1, b * 1.3))
            pattern.add_color_stop_rgb(1, r, g, b)
            
            cr.set_source(pattern)
            cr.fill()
            
            # Add glow effect for high levels
            if level > 0.7:
                self._draw_rounded_rect(cr, x, y, bar_width, bar_height, self.CORNER_RADIUS)
                cr.set_source_rgba(r, g, b, 0.3 * (level - 0.7) / 0.3)
                cr.fill()
                
    def _draw_rounded_rect(self, cr, x, y, width, height, radius):
        """Draw a rounded rectangle path"""
        radius = min(radius, width / 2, height / 2)
        
        cr.new_path()
        cr.arc(x + width - radius, y + radius, radius, -math.pi / 2, 0)
        cr.arc(x + width - radius, y + height - radius, radius, 0, math.pi / 2)
        cr.arc(x + radius, y + height - radius, radius, math.pi / 2, math.pi)
        cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
        cr.close_path()
        
    def reset(self):
        """Reset all levels to zero"""
        self._target_levels = [0.0] * self.NUM_BARS
        self._level_history.clear()
        self.queue_draw()
        
    def cleanup(self):
        """Clean up resources"""
        self._stop_animation()
