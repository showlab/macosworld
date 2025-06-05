import io
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image

def add_coordinate_ticks_to_image(pil_img, dpi=100):
    """
    Adds coordinate ticks to a PIL image without resampling its content.

    The image content (i.e. the axes region) will have the same pixel dimensions
    as the original PIL image. Ticks are drawn along x and y with normalized values
    in [0, 1] (formatted to one decimal). The image content is displayed with its
    original aspect ratio (no extra white padding is added inside the axes).

    Parameters:
      pil_img (PIL.Image.Image): The input image.
      dpi (int): The DPI used for the Matplotlib figure (default 100).
                 The axes region will be set to (width/dpi, height/dpi) inches.

    Returns:
      PIL.Image.Image: The new image (including ticks and labels).
    """
    # Convert PIL image to a NumPy array
    img_array = np.array(pil_img)
    width, height = pil_img.size  # width, height in pixels

    # Compute the axes size (in inches) so that its pixel size is exactly (width, height)
    axes_width_in = width / dpi
    axes_height_in = height / dpi

    # Define margins in inches for tick labels, etc.
    left_margin = 0.8
    bottom_margin = 0.8
    right_margin = 0.2
    top_margin = 0.2

    # Total figure size in inches (axes area + margins)
    fig_width_in = axes_width_in + left_margin + right_margin
    fig_height_in = axes_height_in + bottom_margin + top_margin

    # Create a figure with the computed size and DPI.
    fig = plt.figure(figsize=(fig_width_in, fig_height_in), dpi=dpi)
    # Compute the axes location in figure coordinates
    left = left_margin / fig_width_in
    bottom = bottom_margin / fig_height_in
    axes_width = axes_width_in / fig_width_in
    axes_height = axes_height_in / fig_height_in

    # Add an axes at the desired position
    ax = fig.add_axes([left, bottom, axes_width, axes_height])

    # Display the image.
    # We set extent so that the image spans [0,1] in both directions.
    # Use origin='upper' to preserve the PIL orientation (top row is row 0).
    # Specify aspect='auto' to fill the axes area without enforcing a square aspect.
    ax.imshow(img_array, extent=(0, 1, 0, 1), interpolation='nearest',
              origin='upper', aspect='auto')
    
    # Set ticks at multiples of 0.1 from 0 to 1
    ticks = np.linspace(0, 1, 11)
    x_tick_labels = [f"{tick:.1f}" for tick in ticks]
    y_tick_labels = [f"{(1 - tick):.1f}" for tick in ticks]
    ax.set_xticks(ticks)
    ax.set_xticklabels(x_tick_labels)
    ax.set_yticks(ticks)
    ax.set_yticklabels(y_tick_labels)

    # Optionally, you can adjust tick parameters (font size, etc.)
    ax.tick_params(direction='out', length=5, width=1)

    # Save the entire figure (including margins) into an in-memory buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    ticked_img = Image.open(buf).convert("RGB")
    plt.close(fig)
    return ticked_img