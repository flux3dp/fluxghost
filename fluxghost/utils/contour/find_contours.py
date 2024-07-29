import cv2
import numpy as np


def find_contours(
    img,
    dilate_k=3,
    erode_k=3,
    parent_erode_k=8,
    post_fill_dilate_k=3,
    kernel_type=cv2.MORPH_ELLIPSE,
    size_threshold=10000,
):
    # Step 1: dilate to merge seperate segments
    kernel = cv2.getStructuringElement(kernel_type, (dilate_k, dilate_k))
    img = cv2.dilate(img, kernel, iterations=1)

    # Step 2: Find and fill closed contours
    res = cv2.findContours(img, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    contours, hierarchy = res[0], res[1][0]
    img = np.zeros_like(img)
    parent_contour_img = np.zeros_like(img)
    for i in range(len(contours)):
        hierarchy_data = hierarchy[i]
        if hierarchy_data[3] > 0:
            cv2.drawContours(img, [contours[i]], -1, 255, thickness=cv2.FILLED)
        else:
            cv2.drawContours(parent_contour_img, [contours[i]], -1, 255, thickness=cv2.FILLED)
    # Step 3: After fill, we can erode to denoise
    kernel = cv2.getStructuringElement(kernel_type, (erode_k, erode_k))
    img = cv2.erode(img, kernel, iterations=1)
    kernel = cv2.getStructuringElement(kernel_type, (parent_erode_k, parent_erode_k))
    parent_contour_img = cv2.erode(parent_contour_img, kernel, iterations=1)
    # Step 4: Do a final dilate to compensate the erosion and merge some seperated parts
    kernel = cv2.getStructuringElement(kernel_type, (post_fill_dilate_k, post_fill_dilate_k))
    img = cv2.dilate(img, kernel, iterations=1)
    parent_contour_img = cv2.dilate(parent_contour_img, kernel, iterations=1)

    res = cv2.findContours(img.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = res[0]
    res = cv2.findContours(parent_contour_img.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours += res[0]
    if size_threshold is not None:
        contours = [contour for contour in contours if cv2.contourArea(contour) > size_threshold]
    return contours


def get_contour_by_canny(img, prefix: str = "", size_threshold=10000):
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Enhance contrast using CLAHE
    clahe = cv2.createCLAHE(clipLimit=80.0, tileGridSize=(8, 8))
    img = clahe.apply(img)
    # Apply Gaussian blur
    img = cv2.GaussianBlur(img, (9, 9), 0)
    img = cv2.Canny(img, 30, 200, 5)
    return find_contours(img, 25, 15, 15, size_threshold=size_threshold)


def get_contour_by_hsv_gradient(img, prefix: str = "", size_threshold=10000):
    # Convert to HSV color space
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # Apply Sobel operator to each channel
    sobel_x = cv2.Sobel(hsv, cv2.CV_64F, 1, 0, ksize=5)
    sobel_y = cv2.Sobel(hsv, cv2.CV_64F, 0, 1, ksize=5)
    # Compute gradient magnitude
    gradient_magnitude = cv2.magnitude(sobel_x[:, :, 0], sobel_y[:, :, 0])
    gradient_magnitude += cv2.magnitude(sobel_x[:, :, 1], sobel_y[:, :, 1])
    gradient_magnitude += cv2.magnitude(sobel_x[:, :, 2], sobel_y[:, :, 2])

    img = np.uint8(np.sqrt(gradient_magnitude))
    img = cv2.GaussianBlur(img, (15, 15), 0)

    # Exclude black pixels because bb-series would contain a lot of transparent (black) pixels
    flat_image = img.flatten()
    non_black_pixels = flat_image[flat_image > 0]
    threshold = np.quantile(non_black_pixels, 0.85)

    _, img = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)
    return find_contours(img, dilate_k=5, erode_k=30, parent_erode_k=40, post_fill_dilate_k=30, size_threshold=size_threshold)
