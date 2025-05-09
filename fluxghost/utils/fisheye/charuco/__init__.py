import cv2
import cv2.aruco as aruco


def get_dictionary(squares_x, squares_y):
    required_markers = (squares_x - 1) * (squares_y - 1)

    # Available 5x5 dictionaries in OpenCV
    dict_options = [
        (aruco.DICT_5X5_50, 50),
        (aruco.DICT_5X5_100, 100),
        (aruco.DICT_5X5_250, 250),
        (aruco.DICT_5X5_1000, 1000),
    ]

    # Find the smallest dictionary that fits the requirement
    for dict_id, max_ids in dict_options:
        if required_markers <= max_ids:
            return aruco.getPredefinedDictionary(dict_id)

    raise ValueError("Board size requires more markers than available in 5x5 dictionaries.")


def get_charuco_board(squares_x = 10, squares_y=15, unit = 18 / 4):
    '''
    :param squares_x: Number of squares in the x direction
    :param squares_y: Number of squares in the y direction
    :param unit: Length of the square side in mm
    '''
    # Parameters
    square_length = 4 * unit
    marker_length = 3 * unit
    dictionary = get_dictionary(squares_x, squares_y)
    board = cv2.aruco.CharucoBoard((squares_x, squares_y), square_length, marker_length, dictionary)
    return board

