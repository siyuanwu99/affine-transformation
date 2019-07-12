import albumentations as A
import numpy as np
import cv2
import math
import random
import matplotlib.pyplot as plt
from grid import grid
import albumentations.augmentations.functional as F
from albumentations.core.transforms_interface import to_tuple, DualTransform


def F_rotate(img, angle, interpolation=cv2.INTER_LINEAR, border_mode=cv2.BORDER_CONSTANT, value=None, is_padding=False):
    if is_padding:
        h0, w0 = img.shape[:2]
        height = w0 * math.sin(angle * math.pi / 180) + h0 * math.cos(angle * math.pi / 180)
        width = h0 * math.sin(angle * math.pi / 180) + w0 * math.cos(angle * math.pi / 180)
    else:
        height, width = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w0 // 2, h0 // 2), angle, 1.0)
    matrix[0, 2] += abs((width - w0) / 2)
    matrix[1, 2] += abs((height - h0) / 2)
    img = cv2.warpAffine(img, matrix, (int(width), int(height)), flags=interpolation, borderMode=border_mode,
                         borderValue=value)
    return img


class Rotate(DualTransform):
    """Rotate the input by an angle selected randomly from the uniform distribution.

    Args:
        limit ((int, int) or int): range from which a random angle is picked. If limit is a single int
            an angle is picked from (-limit, limit). Default: 90
        interpolation (OpenCV flag): flag that is used to specify the interpolation algorithm. Should be one of:
            cv2.INTER_NEAREST, cv2.INTER_LINEAR, cv2.INTER_CUBIC, cv2.INTER_AREA, cv2.INTER_LANCZOS4.
            Default: cv2.INTER_LINEAR.
        border_mode (OpenCV flag): flag that is used to specify the pixel extrapolation method. Should be one of:
            cv2.BORDER_CONSTANT, cv2.BORDER_REPLICATE, cv2.BORDER_REFLECT, cv2.BORDER_WRAP, cv2.BORDER_REFLECT_101.
            Default: cv2.BORDER_REFLECT_101
        value (list of ints [r, g, b]): padding value if border_mode is cv2.BORDER_CONSTANT.
        p (float): probability of applying the transform. Default: 0.5.

    Targets:
        image, mask, bboxes, keypoints

    Image types:
        uint8, float32
    """

    def __init__(self, limit=90, interpolation=cv2.INTER_LINEAR, border_mode=cv2.BORDER_REFLECT_101,
                 value=None, always_apply=False, p=.5):
        super(Rotate, self).__init__(always_apply, p)
        self.limit = to_tuple(limit)
        self.interpolation = interpolation
        self.border_mode = border_mode
        self.value = value

    def apply(self, img, angle=0, interpolation=cv2.INTER_LINEAR, **params):
        return F_rotate(img, angle, interpolation, self.border_mode, self.value, is_padding=True)

    def get_params(self):
        return {'angle': random.uniform(self.limit[0], self.limit[1])}

    def apply_to_bbox(self, bbox, angle=0, **params):
        return F.bbox_rotate(bbox, angle, **params)

    def apply_to_keypoint(self, keypoint, angle=0, **params):
        return F.keypoint_rotate(keypoint, angle, **params)

    def get_transform_init_args_names(self):
        return ('limit', 'interpolation', 'border_mode', 'value')


def keypoint_affine(keypoint, param, rows, cols, **params):
    # 由于不知道仿射变换对于极坐标有何影响，所以先返回0值
    pts = np.float32([[0, 0], [cols - 1, 0], [0, rows - 1]])
    dst = np.float32([[cols * param[0], rows * param[1]],
                      [cols * param[2], rows * param[3]],
                      [cols * param[3], rows * param[4]]])
    matrix = cv2.getAffineTransform(pts, dst)
    x, y, a, s = keypoint
    x, y = cv2.transform(np.array([[[x, y]]]), matrix).squeeze()
    return [x, y, 0, 0]


def affine(img, param=[0, 0, 0, 0, 0, 0], interpolation=cv2.INTER_LINEAR, border_mode=cv2.BORDER_CONSTANT):
    h0, w0 = img.shape[:2]
    center_square = np.float32((h0, w0)) // 2
    square_size = min((h0, w0)) // 3
    pts = np.float32([center_square + square_size,
                      [center_square[0] + square_size, center_square[1] - square_size],
                      center_square - square_size])
    dst = pts + np.float32([
        [square_size * param[0], square_size * param[1]],
        [square_size * param[2], square_size * param[3]],
        [square_size * param[4], square_size * param[5]]])

    height = 3 * max(abs(dst[0][0] - center_square[0]),
                     abs(dst[1][0] - center_square[0]),
                     abs(dst[2][0] - center_square[0]),
                     h0 / 3)
    width = 3 * max(abs(dst[0][1] - center_square[1]),
                    abs(dst[1][1] - center_square[1]),
                    abs(dst[2][1] - center_square[1]),
                    w0 / 3)
    matrix = cv2.getAffineTransform(pts, dst)
    img = cv2.warpAffine(img, matrix, (int(width), int(height)),
                         flags=interpolation, borderMode=border_mode)
    return img


class AffineTransform(DualTransform):
    """
    实行仿射变换，由于不知仿射变换的极坐标表示，因此目前先返回为零
    """

    def __init__(self, param, interpolation=cv2.INTER_LINEAR, border_mode=cv2.BORDER_REFLECT_101,
                 value=None, always_apply=False, p=.5):
        super(AffineTransform, self).__init__(always_apply, p)
        self.interpolation = interpolation
        self.border_mode = border_mode
        # self.value = value
        self.param = param

    def apply(self, img, param=[0, 0, 1, 0, 0, 1], interpolation=cv2.INTER_LINEAR, **params):
        return affine(img, self.param, self.interpolation, self.border_mode)

    def get_params(self):
        return {'param': self.param}

    # def apply_to_bbox(self, bbox, angle=0, **params):
    #     return F.bbox_rotate(bbox, angle, **params)

    def apply_to_keypoint(self, keypoint, param=[0, 0, 1, 0, 0, 1], **params):
        return keypoint_affine(keypoint, param, **params)

    def get_transform_init_args_names(self):
        return ('interpolation', 'border_mode')


def Random_crop(img, msk, height=512, width=512):
    aug = A.Compose([A.RandomCrop(height=height, width=width)])
    data = aug(image=img, mask=msk)
    return data['image'], data['mask']


def Horizontal_flip(img, msk):
    aug = A.Compose([A.HorizontalFlip(always_apply=True)])
    data = aug(image=img, mask=msk)
    return data['image'], data['mask']


def Vertical_flip(img, msk):
    aug = A.Compose([A.VerticalFlip(always_apply=True)])
    data = aug(image=img, mask=msk)
    return data['image'], data['mask']


def Rotate45(img, msk):
    aug = A.Compose([Rotate(limit=(45, 45), border_mode=cv2.BORDER_CONSTANT, always_apply=True)])
    data = aug(image=img, mask=msk)
    return data['image'], data['mask']


def Rotate30(img, msk):
    aug = A.Compose([Rotate(limit=(30, 30), border_mode=cv2.BORDER_CONSTANT, always_apply=True)])
    data = aug(image=img, mask=msk)
    return data['image'], data['mask']


def Rotate60(img, msk):
    aug = A.Compose([Rotate(limit=(60, 60), border_mode=cv2.BORDER_CONSTANT, always_apply=True)])
    data = aug(image=img, mask=msk)
    return data['image'], data['mask']


def Affine(img, msk, param):
    aug = A.Compose([AffineTransform(param=param, border_mode=cv2.BORDER_CONSTANT, always_apply=True)])
    data = aug(image=img, mask=msk)
    return data['image'], data['mask']


if __name__ == '__main__':
    path = "/home/edmund/projects/pics/1531053735.jpg"
    img = cv2.imread(path)
    mask = grid(img)
    # plt.figure()
    # plt.imshow(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    # plt.figure()
    # plt.imshow(mask)
    # plt.show()
    # img_, msk_ = Affine(img, mask, [-0.01, 0.01, 0.1, -0.01, 0.01, 0.01])
    # img_ = F_affine(img, [0.1, 0.1, 1, 0.2, 0.2, 1])
    img_, msk_ = Rotate45(img, mask)
    plt.figure()
    plt.imshow(img_)
    # plt.imshow(cv2.cvtColor(img_, cv2.COLOR_RGB2BGR))
    plt.figure()
    plt.imshow(msk_)
    plt.show()
