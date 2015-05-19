
cdef extern from "noise_del.h":
    cdef cppclass PointCloudXYZRGB:
        pass

    PointCloudXYZRGB createPointCloudXYZRGB()
    int loadPointCloudXYZRGB(const char* file, PointCloudXYZRGB cloud)
    void dumpPointCloudXYZRGB(const char* file, PointCloudXYZRGB cloud)

    int SOR(PointCloudXYZRGB cloud, int neighbors, float thresh)
    int VG(PointCloudXYZRGB cloud)

cdef extern from "reg.h":
    cdef cppclass PointNT:
        pass
    cdef cppclass PointCloudTPtr:
        pass
    cdef cppclass Matrix4f: # Eigen::Matrix4f (namespce error)
        pass
    cdef cppclass FeatureCloudTPtr:
        pass

    PointCloudTPtr createPointCloudPointNormal()
    int loadPointCloudPointNormal(const char* file, PointCloudTPtr cloud)
    void dumpPointCloudPointNormal(const char* file, PointCloudTPtr cloud)
    int NE_OMP(PointCloudTPtr object,float radius)
    int FE(PointCloudTPtr object, FeatureCloudTPtr object_features, float radius)
    int SCP(PointCloudTPtr object, FeatureCloudTPtr object_features, PointCloudTPtr scene, FeatureCloudTPtr scene_features, Matrix4f &transformation)


cdef class PointCloudXYZRGBObj:
    cdef PointCloudXYZRGB obj

    def __init__(self):
        self.obj = createPointCloudXYZRGB()

    cpdef loadFile(self, unicode filename):
        if loadPointCloudXYZRGB(filename.encode(), self.obj) == -1:
            raise RuntimeError("Load failed")

    cpdef PointCloudXYZRGBObj clone(self):
        cdef PointCloudXYZRGBObj obj = PointCloudXYZRGBObj()
        # TODO:
        raise RuntimeError("Not implement clone yet")
        return obj

    cpdef dump(self, unicode filename):
        dumpPointCloudXYZRGB(filename.encode(), self.obj)

    cpdef int SOR(self, int neighbors, float threshold):
        return SOR(self.obj, neighbors, threshold)

    cpdef int VG(self):
        return VG(self.obj)
