import cv2
import numpy as np

from fluxghost.utils.opencv import findContours


def find_contours(
    img,
    dilate_k=3,
    erode_k=3,
    parent_erode_k=8,
    dilate_k_2=3,
    parent_dilate_k_2=8,
    kernel_type=cv2.MORPH_ELLIPSE,
    size_threshold=10000,
):
    # Step 1: dilate to merge seperate segments
    kernel = cv2.getStructuringElement(kernel_type, (dilate_k, dilate_k))
    img = cv2.dilate(img, kernel, iterations=1)

    # Step 2: Find and fill closed contours
    res = findContours(img, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    contours, hierarchy = res[0], res[1][0]
    hierarchy_map = {-1: 0}
    for i in range(len(hierarchy)):
        tier = 1
        parent = hierarchy[i][3]
        while hierarchy_map.get(parent, -1) < 0:
            parent = hierarchy[parent][3]
            tier += 1
        hierarchy_map[i] = hierarchy_map[parent] + tier
    parent_contour_img = np.zeros_like(img)
    child_contour_img = np.zeros_like(img)
    for i in range(len(contours)):
        tier = hierarchy_map[i]
        if tier % 4 == 1:
            cv2.drawContours(parent_contour_img, [contours[i]], -1, 255, thickness=cv2.FILLED)
        elif tier % 4 == 2:
            cv2.drawContours(child_contour_img, [contours[i]], -1, 255, thickness=cv2.FILLED)
        elif tier % 4 == 3:
            cv2.drawContours(parent_contour_img, [contours[i]], -1, 0, thickness=cv2.FILLED)
        elif tier % 4 == 0:
            cv2.drawContours(child_contour_img, [contours[i]], -1, 0, thickness=cv2.FILLED)
    # Step 3: After fill, we can erode to denoise
    kernel = cv2.getStructuringElement(kernel_type, (erode_k, erode_k))
    child_contour_img = cv2.erode(child_contour_img, kernel, iterations=1)
    kernel = cv2.getStructuringElement(kernel_type, (parent_erode_k, parent_erode_k))
    parent_contour_img = cv2.erode(parent_contour_img, kernel, iterations=1)
    # Step 4: Do a final dilate to compensate the erosion and merge some seperated parts
    kernel = cv2.getStructuringElement(kernel_type, (dilate_k_2, dilate_k_2))
    child_contour_img = cv2.dilate(child_contour_img, kernel, iterations=1)
    kernel = cv2.getStructuringElement(kernel_type, (parent_dilate_k_2, parent_dilate_k_2))
    parent_contour_img = cv2.dilate(parent_contour_img, kernel, iterations=1)

    res = findContours(child_contour_img, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    child_contours = res[0]
    res = findContours(parent_contour_img, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    parent_contours = res[0]
    if size_threshold is not None:
        child_contours = [contour for contour in child_contours if cv2.contourArea(contour) > size_threshold]
        parent_contours = [contour for contour in parent_contours if cv2.contourArea(contour) > size_threshold]
    return child_contours, parent_contours


def get_contour_by_canny(img, is_spliced_img=False, size_threshold=10000):
    if is_spliced_img:
        img = cv2.GaussianBlur(img, (17, 17), 0)
        img = cv2.Canny(img, 30, 85)
    else:
        img = cv2.Canny(img, 30, 200, 5)
    return find_contours(
        img,
        dilate_k=25,
        erode_k=15,
        parent_erode_k=20,
        dilate_k_2=15,
        parent_dilate_k_2=20,
        size_threshold=size_threshold,
    )


def get_contour_by_hsv_gradient(img, is_spliced_img=False, size_threshold=10000):
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
    threshold = np.quantile(non_black_pixels, 0.7 if is_spliced_img else 0.9)
    _, img = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)
    # For b-series only, remove small noise of splicing
    if is_spliced_img:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        img = cv2.erode(img, kernel, iterations=1)
        img = cv2.dilate(img, kernel, iterations=1)

    return find_contours(
        img,
        dilate_k=5,
        erode_k=30,
        parent_erode_k=20,
        dilate_k_2=30,
        parent_dilate_k_2=20,
        size_threshold=size_threshold,
    )
