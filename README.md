# TXT-to-JPEG-images
使用python将txt的电子小说转换为jpeg格式的图片
# 用途
在一些设备（如功能机）等上阅读txt电子小说时，可能出现没有对应的应用打开的情况，这个时候如果能够把txt转化为jpeg格式的图片，就能够实现阅读
# 特点
将章节分到了多个文件夹，保证了每个文件夹不多于指定数目的文件，这样跳转文件时便无需频繁按上下键
# 使用方法
安装python 3，下载地址参见：<https://python.org/downloads>

运行以下命令安装必要的库
```
pip install Pillow pathlib
```
安装完成后双击打开程序，按照说明进行操作

程序代码的开头部分可以设置一些变量的默认配置
```
# 图片分辨率设置
default_width = 215
default_height = 290
# 文件夹层数设置
default_max_folders_per_level = 10 #最大文件夹层数
default_chapters_per_folder = 100
# 字体设置
default_font_size = 12
```
# 说明
本程序很大一部分是AI完成的，因为是作者自用，有很多不完善的地方是很正常的，发出来只是本着一个分享的态度，如有错误还请指出
