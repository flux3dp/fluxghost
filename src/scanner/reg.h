#include <pcl/point_types.h>
#include <pcl/point_cloud.h>


// Types
typedef pcl::PointNormal PointNT; // float x, y, z; float normal[3], curvature
typedef pcl::PointCloud<PointNT> PointCloudT;
typedef pcl::PointCloud<PointNT>::Ptr PointCloudTPtr;
typedef pcl::FPFHSignature33 FeatureT;

typedef pcl::FPFHEstimationOMP<PointNT,PointNT,FeatureT> FeatureEstimationT;
typedef pcl::PointCloud<FeatureT> FeatureCloudT;
typedef pcl::PointCloud<FeatureT>::Ptr FeatureCloudTPtr;

typedef pcl::visualization::PointCloudColorHandlerCustom<PointNT> ColorHandlerT;

PointCloudTPtr createPointCloudPointNormal();
void dumpPointCloudXYZRGB(const char* file, PointCloudTPtr cloud);

int downsample(PointCloudTPtr object, float leaf);
int NE_OMP(PointCloudTPtr object,float radius);
int FE(PointCloudTPtr object, FeatureCloudTPtr object_features, float radius);
int SCP();
